"""Messages of one account → services in memory (spec F2-7, F3-1, F4-1..3; plan §5).

Only emails that match a detection rule count: they give the service its relation types,
dates, email count, name and evidence (one evidence item per email and relation type).
Each analysis covers one account, so the same domain in two accounts gives two services.

- Name: most frequent display name of the sender; otherwise catalog name, otherwise domain.
- Management link: catalog → link in the emails → homepage. Bodies are only fetched for the
  registered/access evidence of services that are not in the catalog (plan §4 "Gmail").
- Unsubscribe method: from the most recent email with a usable ``List-Unsubscribe``.

``save_analysis`` merges a complete analysis into the database in one transaction
(plan §3 "Fusión"; spec F2-8, F7-1, F8-3, F8-4, F8-6).
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from exitmap.domain.catalog import Catalog, default_catalog
from exitmap.domain.detection import Rules, detect
from exitmap.domain.domains import registrable_domain
from exitmap.domain.links import management_link
from exitmap.domain.models import Account, Evidence, RelationType, Service, State
from exitmap.domain.unsubscribe import UnsubscribeOption, parse_unsubscribe
from exitmap.providers.base import Folders, MailProvider, Period
from exitmap.storage.db import Database

BODY_TYPES = frozenset({RelationType.REGISTERED, RelationType.ACCESS})


@dataclass
class DetectedService:
    """A service found by an analysis and the evidence it is based on."""

    service: Service
    evidence: list[Evidence]


@dataclass
class _Draft:
    domain: str
    types: set[RelationType] = field(default_factory=set)
    first_at: datetime | None = None
    last_at: datetime | None = None
    count: int = 0
    names: Counter[str] = field(default_factory=Counter)
    evidence: list[Evidence] = field(default_factory=list)
    body_ids: list[str] = field(default_factory=list)
    unsubscribe: UnsubscribeOption | None = None
    unsubscribe_at: datetime | None = None


def decode_subject(subject: str) -> str:
    """Decode MIME encoded words of a subject, keeping its case and accents."""
    try:
        return str(make_header(decode_header(subject))).strip()
    except (ValueError, LookupError):
        return subject.strip()


def parse_date(value: str | None) -> datetime | None:
    """``Date`` header → aware datetime (naive dates are taken as UTC); ``None`` if invalid."""
    if not value:
        return None
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


class ServiceAggregator:
    """Collects the messages of one account and builds its services."""

    def __init__(
        self,
        account_id: int | None = None,
        catalog: Catalog | None = None,
        rules: Rules | None = None,
    ) -> None:
        self.account_id = account_id
        self.catalog = catalog or default_catalog()
        self.rules = rules
        self._drafts: dict[str, _Draft] = {}

    def add(self, message_id: str, headers: Mapping[str, str]) -> None:
        """Take one message into account; emails without a rule or a domain are ignored."""
        by_name = {name.lower(): value for name, value in headers.items()}
        types = detect(by_name, self.rules)
        sender = by_name.get("from", "")
        domain = registrable_domain(sender)
        sent_at = parse_date(by_name.get("date"))
        if not types or not domain or sent_at is None:
            return

        draft = self._drafts.setdefault(domain, _Draft(domain))
        draft.types |= types
        draft.count += 1
        draft.first_at = min(draft.first_at or sent_at, sent_at)
        draft.last_at = max(draft.last_at or sent_at, sent_at)
        display_name = parseaddr(sender)[0].strip()
        if display_name:
            draft.names[display_name] += 1

        subject = decode_subject(by_name.get("subject", ""))
        for relation_type in sorted(types):
            draft.evidence.append(Evidence(message_id, subject, sent_at, relation_type))
        if types & BODY_TYPES:
            draft.body_ids.append(message_id)

        option = parse_unsubscribe(
            by_name.get("list-unsubscribe"), by_name.get("list-unsubscribe-post")
        )
        if option and (draft.unsubscribe_at is None or sent_at >= draft.unsubscribe_at):
            draft.unsubscribe, draft.unsubscribe_at = option, sent_at

    def services(self, provider: MailProvider | None = None) -> list[DetectedService]:
        """Build the services, sorted by domain.

        ``provider`` is used to read the bodies needed for the management link; without it
        the link comes from the catalog or the homepage.
        """
        return [self._build(draft, provider) for _, draft in sorted(self._drafts.items())]

    def _build(self, draft: _Draft, provider: MailProvider | None) -> DetectedService:
        entry = self.catalog.lookup(draft.domain)
        bodies = (
            (provider.get_body(message_id) for message_id in draft.body_ids)
            if provider is not None and entry is None
            else ()
        )
        link = management_link(draft.domain, bodies, self.catalog)
        if draft.names:
            name = draft.names.most_common(1)[0][0]
        else:
            name = entry.name if entry else draft.domain
        service = Service(
            account_id=self.account_id,
            domain=draft.domain,
            name=name,
            relation_types=set(draft.types),
            first_email_at=draft.first_at,
            last_email_at=draft.last_at,
            email_count=draft.count,
            manage_url=link.url,
            manage_url_source=link.source,
            unsubscribe_method=draft.unsubscribe.method if draft.unsubscribe else None,
            unsubscribe_target=draft.unsubscribe.target if draft.unsubscribe else None,
        )
        evidence = sorted(draft.evidence, key=lambda e: (e.sent_at, e.relation_type))
        return DetectedService(service, evidence)


def analyse(
    provider: MailProvider,
    period: Period = Period(),
    folders: Folders = Folders(),
    account_id: int | None = None,
    catalog: Catalog | None = None,
    rules: Rules | None = None,
) -> list[DetectedService]:
    """Read every message of ``period`` and ``folders`` and return the detected services."""
    aggregator = ServiceAggregator(account_id, catalog, rules)
    for message_id in provider.list_message_ids(period, folders):
        aggregator.add(message_id, provider.get_headers(message_id))
    return aggregator.services(provider)


class AnalysisMode(StrEnum):
    """What a re-analysis reads (spec F8-1)."""

    ALL = "all"
    NEW_ONLY = "new_only"


def new_only_period(account: Account) -> Period:
    """Period of a "new emails only" analysis: since the last complete one (plan §3)."""
    return Period(start=account.last_complete_analysis_at)


def save_analysis(
    db: Database,
    account_id: int,
    detected: list[DetectedService],
    mode: AnalysisMode = AnalysisMode.ALL,
    completed_at: datetime | None = None,
) -> None:
    """Merge a complete analysis of one account into the database, all or nothing.

    - New services are saved as *pending* (F7-1).
    - ``ALL``: statistics, links and evidence are recalculated; ``NEW_ONLY``: emails not
      already in the evidence are added to the counts and the evidence. The state is kept
      in both modes (F8-3).
    - Services that were not detected again stay as they are (F8-6).
    - An *unsubscribed* service with an email not seen before and sent after the state
      change gets an alert (F8-4).
    - ``last_complete_analysis_at`` becomes ``completed_at`` (by default, now).
    """
    completed_at = completed_at or datetime.now(UTC)
    with db.transaction():
        for item in detected:
            _merge(db, account_id, item, mode)
        db.set_last_complete_analysis(account_id, completed_at)


def _merge(db: Database, account_id: int, item: DetectedService, mode: AnalysisMode) -> None:
    detected = item.service
    existing = db.find_service(account_id, detected.domain)
    if existing is None:
        service = replace(detected, account_id=account_id, id=None)
        db.save_service(service)
        _add_evidence(db, service.id, item.evidence)
        return

    seen = {e.provider_message_id for e in db.list_evidence(existing.id)}
    unseen = [e for e in item.evidence if e.provider_message_id not in seen]
    if mode is AnalysisMode.ALL:
        service = replace(
            detected,
            account_id=account_id,
            state=existing.state,
            state_changed_at=existing.state_changed_at,
            has_alert=existing.has_alert,
            id=existing.id,
        )
        db.delete_evidence(existing.id)
        new_evidence = item.evidence
    else:
        service = _add_new_emails(existing, detected, unseen)
        new_evidence = unseen

    if _needs_alert(service, unseen):
        service.has_alert = True
    db.save_service(service)
    _add_evidence(db, service.id, new_evidence)


def _add_new_emails(existing: Service, detected: Service, unseen: list[Evidence]) -> Service:
    """``NEW_ONLY``: add the emails not seen before to an existing service."""
    if not unseen:
        return replace(existing)
    dates = [e.sent_at for e in unseen]
    first = min(dates + ([existing.first_email_at] if existing.first_email_at else []))
    last = max(dates + ([existing.last_email_at] if existing.last_email_at else []))
    service = replace(
        existing,
        relation_types=existing.relation_types | {e.relation_type for e in unseen},
        first_email_at=first,
        last_email_at=last,
        email_count=existing.email_count + len({e.provider_message_id for e in unseen}),
    )
    if existing.manage_url is None:
        service.manage_url = detected.manage_url
        service.manage_url_source = detected.manage_url_source
    if detected.unsubscribe_method is not None:
        service.unsubscribe_method = detected.unsubscribe_method
        service.unsubscribe_target = detected.unsubscribe_target
    return service


def _needs_alert(service: Service, unseen: list[Evidence]) -> bool:
    if service.state is not State.UNSUBSCRIBED:
        return False
    changed_at = service.state_changed_at
    return any(changed_at is None or e.sent_at > changed_at for e in unseen)


def _add_evidence(db: Database, service_id: int, evidence: list[Evidence]) -> None:
    for item in evidence:
        db.add_evidence(replace(item, service_id=service_id, id=None))
