"""View logic without widgets, so it can be tested without a screen (plan §2, §6).

- Analysis options: defaults, DD/MM/AAAA dates and the period and folders they give
  (spec F2-1..3, F8-1, F8-2).
- Messages for empty results (spec F2-10, F3-5).
- Texts of the confirmations shown before unsubscribing and removing an account
  (spec F5-1, F9-1).
- Rows and filter options of the main window (spec F3, F8-4).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from exitmap.app.accounts import RemovalSummary
from exitmap.app.analysis import AnalysisMode, new_only_period
from exitmap.app.services import ServiceFilter
from exitmap.domain.models import Account, RelationType, Service, State
from exitmap.errors import ExitMapError, InvalidDateError, InvalidDateRangeError
from exitmap.providers.base import Folders, Period
from exitmap.ui import strings_es as text

DATE_FORMAT = "%d/%m/%Y"


class PeriodChoice(StrEnum):
    """Period options of an analysis (spec F2-1)."""

    WHOLE_MAILBOX = "whole_mailbox"
    LAST_YEAR = "last_year"
    CUSTOM = "custom"


PERIOD_LABELS = {
    PeriodChoice.WHOLE_MAILBOX: text.PERIOD_WHOLE_MAILBOX,
    PeriodChoice.LAST_YEAR: text.PERIOD_LAST_YEAR,
    PeriodChoice.CUSTOM: text.PERIOD_CUSTOM,
}

MODE_LABELS = {
    AnalysisMode.ALL: text.MODE_ALL,
    AnalysisMode.NEW_ONLY: text.MODE_NEW_ONLY,
}


@dataclass(frozen=True)
class AnalysisOptions:
    """What the user chose in the analysis dialog.

    By default: whole mailbox (F2-1), Spam and Trash off (F2-3) and, in a re-analysis,
    all the emails (F8-1). The dates are the texts typed in DD/MM/AAAA.
    """

    period: PeriodChoice = PeriodChoice.WHOLE_MAILBOX
    start_text: str = ""
    end_text: str = ""
    include_spam: bool = False
    include_trash: bool = False
    mode: AnalysisMode = AnalysisMode.ALL


def default_analysis_options() -> AnalysisOptions:
    return AnalysisOptions()


def parse_date(value: str) -> date:
    """A date typed as DD/MM/AAAA; anything else → ``InvalidDateError``."""
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError as exc:
        raise InvalidDateError() from exc


def _local_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day).astimezone()


def custom_period(start_text: str, end_text: str) -> Period:
    """Period from the first moment of the start day to the last of the end day.

    A start after the end → ``InvalidDateRangeError``, so the analysis cannot start (F2-2).
    """
    start, end = parse_date(start_text), parse_date(end_text)
    if start > end:
        raise InvalidDateRangeError()
    return Period(start=_local_midnight(start), end=_local_midnight(end + timedelta(days=1)))


def _one_year_before(moment: datetime) -> datetime:
    try:
        return moment.replace(year=moment.year - 1)
    except ValueError:  # 29 February
        return moment.replace(year=moment.year - 1, day=28)


def is_reanalysis(account: Account) -> bool:
    """Whether the account already has a complete analysis (F8-1, F8-2)."""
    return account.last_complete_analysis_at is not None


def analysis_period(
    options: AnalysisOptions, account: Account, now: datetime | None = None
) -> Period:
    """Period to read; "new emails only" reads since the last complete analysis (plan §3)."""
    if options.mode is AnalysisMode.NEW_ONLY and is_reanalysis(account):
        return new_only_period(account)
    if options.period is PeriodChoice.LAST_YEAR:
        now = now or datetime.now().astimezone()
        return Period(start=_one_year_before(now))
    if options.period is PeriodChoice.CUSTOM:
        return custom_period(options.start_text, options.end_text)
    return Period()


def analysis_folders(options: AnalysisOptions) -> Folders:
    return Folders(include_spam=options.include_spam, include_trash=options.include_trash)


def analysis_error(options: AnalysisOptions, account: Account) -> ExitMapError | None:
    """Why the analysis cannot start with these options, or ``None`` (F2-2)."""
    try:
        analysis_period(options, account)
    except ExitMapError as exc:
        return exc
    return None


def reanalysis_notice(account: Account) -> str | None:
    """Notice shown before a re-analysis: the states are kept (F8-2)."""
    return text.REANALYSIS_NOTICE if is_reanalysis(account) else None


def analysis_result_message(service_count: int) -> str | None:
    """Message when a complete analysis found no service (F2-10)."""
    return text.NO_SERVICES_FOUND if service_count == 0 else None


def list_message(visible: int, filtered: bool) -> str | None:
    """Message for a list that shows nothing because of the search or filters (F3-5)."""
    return text.NO_MATCHES if visible == 0 and filtered else None


def unsubscribe_confirmation(service: Service, account: Account) -> str:
    """Service, account and method, shown before anything is done (F5-1)."""
    if service.unsubscribe_method is None:
        raise ExitMapError()
    method = text.UNSUBSCRIBE_METHOD_LABELS[service.unsubscribe_method.value].format(
        url=service.unsubscribe_target or ""
    )
    return text.UNSUBSCRIBE_CONFIRM.format(
        service=_service_label(service), account=account.email, method=method
    )


def removal_confirmation(summary: RemovalSummary) -> str:
    """What removing the account deletes, shown before anything is done (F9-1)."""
    count = summary.service_count
    services = (
        text.SERVICE_COUNT_ONE if count == 1 else text.SERVICE_COUNT_MANY.format(count=count)
    )
    return text.REMOVE_ACCOUNT_CONFIRM.format(account=summary.account.email, count=services)


def _service_label(service: Service) -> str:
    if service.name == service.domain:
        return service.name
    return f"{service.name} ({service.domain})"


def account_label(account: Account) -> str:
    """"ana@gmail.com (Gmail)"."""
    return text.ACCOUNT_LABEL.format(
        email=account.email, provider=text.PROVIDER_LABELS[account.provider.value]
    )


def account_filter_options(accounts: list[Account]) -> list[tuple[str, int | None]]:
    """Choices of the account filter; the first one does not filter (F3-4)."""
    return [(text.ALL_ACCOUNTS, None)] + [(account_label(a), a.id) for a in accounts]


def relation_filter_options() -> list[tuple[str, RelationType | None]]:
    return [(text.ALL_RELATIONS, None)] + [(text.RELATION_LABELS[r.value], r) for r in RelationType]


def state_filter_options() -> list[tuple[str, State | None]]:
    return [(text.ALL_STATES, None)] + [(text.STATE_LABELS[s.value], s) for s in State]


def is_filtered(criteria: ServiceFilter) -> bool:
    """Whether the search or any filter is applied (F3-5)."""
    return bool(criteria.text.strip()) or any(
        value is not None for value in (criteria.account_id, criteria.relation_type, criteria.state)
    )


def relations_text(relation_types: set[RelationType]) -> str:
    """Relation types in a fixed order, separated by commas."""
    return ", ".join(text.RELATION_LABELS[r.value] for r in RelationType if r in relation_types)


def service_row(service: Service, accounts: dict[int, Account]) -> tuple[str, ...]:
    """Columns of the list: name, domain, account, relation types and state.

    A service with an alert carries a mark before its name (F8-4).
    """
    account = accounts.get(service.account_id)
    name = (text.ALERT_MARK if service.has_alert else "") + service.name
    return (
        name,
        service.domain,
        account.email if account else "",
        relations_text(service.relation_types),
        text.STATE_LABELS[service.state.value],
    )
