"""Messages of one account → services in memory (spec F2-7, F3-1, F4-1..3; plan §5).

Only emails that match a detection rule count: they give the service its relation types,
dates, email count, name and evidence (one evidence item per email and relation type).
Each analysis covers one account, so the same domain in two accounts gives two services.

- Name: most frequent display name of the sender; otherwise catalog name, otherwise domain.
- Management link: catalog → link in the emails → homepage. Bodies are only fetched for the
  registered/access evidence of services that are not in the catalog (plan §4 "Gmail").
- Unsubscribe method: from the most recent email with a usable ``List-Unsubscribe``.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from exitmap.domain.catalog import Catalog, default_catalog
from exitmap.domain.detection import Rules, detect
from exitmap.domain.domains import registrable_domain
from exitmap.domain.links import management_link
from exitmap.domain.models import Evidence, RelationType, Service
from exitmap.domain.unsubscribe import UnsubscribeOption, parse_unsubscribe
from exitmap.providers.base import Folders, MailProvider, Period

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
