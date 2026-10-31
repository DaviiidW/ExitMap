"""View logic of the analysis options, empty results and confirmations
(spec F2-1, F2-2, F2-3, F2-10, F3-5, F5-1, F8-1, F8-2, F9-1)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from exitmap.app.accounts import RemovalSummary
from exitmap.app.analysis import AnalysisMode
from exitmap.domain.models import Account, Provider, Service, UnsubscribeMethod
from exitmap.errors import ExitMapError, InvalidDateError, InvalidDateRangeError
from exitmap.providers.base import Folders, Period
from exitmap.ui import strings_es as text
from exitmap.ui.presenters import (
    AnalysisOptions,
    PeriodChoice,
    analysis_error,
    analysis_folders,
    analysis_period,
    analysis_result_message,
    custom_period,
    default_analysis_options,
    is_reanalysis,
    list_message,
    parse_date,
    reanalysis_notice,
    removal_confirmation,
    unsubscribe_confirmation,
)

ACCOUNT = Account(Provider.GMAIL, "ana@example.com", id=1)
ANALYSED = Account(
    Provider.GMAIL, "ana@example.com", id=1,
    last_complete_analysis_at=datetime(2025, 5, 1, 12, tzinfo=UTC),
)


def test_default_options_are_whole_mailbox_without_spam_or_trash():
    """F2-1, F2-3."""
    options = default_analysis_options()
    assert options.period is PeriodChoice.WHOLE_MAILBOX
    assert not options.include_spam and not options.include_trash
    assert options.mode is AnalysisMode.ALL
    assert analysis_period(options, ACCOUNT) == Period()
    assert analysis_folders(options) == Folders()


def test_folders_follow_the_choice():
    """F2-3."""
    options = AnalysisOptions(include_spam=True, include_trash=True)
    assert analysis_folders(options) == Folders(include_spam=True, include_trash=True)


@pytest.mark.parametrize(
    "value, expected",
    [("31/01/2025", date(2025, 1, 31)), (" 1/2/2024 ", date(2024, 2, 1))],
)
def test_parse_date_ddmmyyyy(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize("value", ["", "2025-01-31", "31/13/2025", "30/02/2025", "hoy"])
def test_invalid_date_gives_understandable_error(value):
    with pytest.raises(InvalidDateError) as info:
        parse_date(value)
    assert "DD/MM/AAAA" in info.value.user_message


def test_custom_period_includes_both_days():
    period = custom_period("01/01/2025", "31/01/2025")
    assert period.start.date() == date(2025, 1, 1)
    assert period.end - period.start == timedelta(days=31)
    assert period.contains(period.start)
    assert period.contains(datetime(2025, 1, 31, 23, 59).astimezone())
    assert not period.contains(datetime(2025, 2, 1).astimezone())


def test_same_start_and_end_day_is_valid():
    period = custom_period("15/03/2025", "15/03/2025")
    assert period.end - period.start == timedelta(days=1)


def test_start_after_end_cannot_start_and_says_why():
    """F2-2."""
    with pytest.raises(InvalidDateRangeError):
        custom_period("02/01/2025", "01/01/2025")
    options = AnalysisOptions(PeriodChoice.CUSTOM, "02/01/2025", "01/01/2025")
    error = analysis_error(options, ACCOUNT)
    assert isinstance(error, InvalidDateRangeError)
    assert "posterior" in error.user_message


def test_valid_options_have_no_error():
    assert analysis_error(AnalysisOptions(PeriodChoice.CUSTOM, "01/01/2025", "02/01/2025"),
                          ACCOUNT) is None
    assert analysis_error(default_analysis_options(), ACCOUNT) is None


def test_last_year_starts_one_year_ago():
    now = datetime(2025, 6, 15, 10, tzinfo=UTC)
    period = analysis_period(AnalysisOptions(PeriodChoice.LAST_YEAR), ACCOUNT, now)
    assert period == Period(start=datetime(2024, 6, 15, 10, tzinfo=UTC))


def test_last_year_from_29_february():
    now = datetime(2024, 2, 29, tzinfo=UTC)
    period = analysis_period(AnalysisOptions(PeriodChoice.LAST_YEAR), ACCOUNT, now)
    assert period.start == datetime(2023, 2, 28, tzinfo=UTC)


def test_new_only_reads_since_the_last_complete_analysis():
    """F8-1."""
    options = AnalysisOptions(mode=AnalysisMode.NEW_ONLY)
    assert analysis_period(options, ANALYSED) == Period(start=ANALYSED.last_complete_analysis_at)


def test_new_only_without_previous_analysis_uses_the_period():
    options = AnalysisOptions(mode=AnalysisMode.NEW_ONLY)
    assert analysis_period(options, ACCOUNT) == Period()


def test_reanalysis_notice_only_after_a_complete_analysis():
    """F8-2."""
    assert not is_reanalysis(ACCOUNT)
    assert reanalysis_notice(ACCOUNT) is None
    assert is_reanalysis(ANALYSED)
    assert "estados" in reanalysis_notice(ANALYSED)


def test_empty_analysis_suggests_wider_period_or_folders():
    """F2-10."""
    message = analysis_result_message(0)
    assert "periodo" in message and "Spam" in message
    assert analysis_result_message(3) is None


def test_list_message_when_nothing_matches():
    """F3-5."""
    assert list_message(0, filtered=True) == text.NO_MATCHES
    assert list_message(0, filtered=False) is None
    assert list_message(2, filtered=True) is None


def _subscribed(method, target):
    return Service(1, "tienda.es", "Tienda", unsubscribe_method=method,
                   unsubscribe_target=target)


@pytest.mark.parametrize(
    "method, target, expected",
    [
        (UnsubscribeMethod.ONE_CLICK, "https://tienda.es/u", "baja automática"),
        (UnsubscribeMethod.WEB, "https://tienda.es/u", "se abrirá esta web: https://tienda.es/u"),
        (UnsubscribeMethod.MAILTO, "mailto:baja@tienda.es", "se preparará un correo de baja"),
    ],
)
def test_unsubscribe_confirmation_has_service_account_and_method(method, target, expected):
    """F5-1."""
    message = unsubscribe_confirmation(_subscribed(method, target), ACCOUNT)
    assert "Tienda (tienda.es)" in message
    assert ACCOUNT.email in message
    assert expected in message


def test_unsubscribe_confirmation_without_method_is_an_error():
    with pytest.raises(ExitMapError):
        unsubscribe_confirmation(_subscribed(None, None), ACCOUNT)


def test_service_named_as_its_domain_is_not_repeated():
    service = Service(1, "tienda.es", "tienda.es", unsubscribe_method=UnsubscribeMethod.MAILTO,
                      unsubscribe_target="mailto:a@tienda.es")
    assert "tienda.es (tienda.es)" not in unsubscribe_confirmation(service, ACCOUNT)


@pytest.mark.parametrize("count, label", [(1, "1 servicio)"), (7, "7 servicios")])
def test_removal_confirmation_says_what_is_deleted(count, label):
    """F9-1."""
    message = removal_confirmation(RemovalSummary(ACCOUNT, count))
    assert ACCOUNT.email in message
    assert "credenciales" in message and "resultados" in message and "estados" in message
    assert label in message


def test_progress_text_uses_spanish_thousands():
    """F2-4."""
    from exitmap.ui.presenters import progress_text
    assert progress_text(1200, 15000) == "1.200 de 15.000"
    assert progress_text(0, 7) == "0 de 7"


def test_analysis_done_message():
    """F2-10."""
    from exitmap.ui.presenters import analysis_done_message
    assert analysis_done_message(0) == text.NO_SERVICES_FOUND
    assert analysis_done_message(1) == text.ANALYSIS_DONE_ONE
    assert "4 servicios" in analysis_done_message(4)


def test_removal_result_messages():
    """F9-3, F9-4."""
    from exitmap.app.accounts import RemovalResult
    from exitmap.ui.presenters import removal_result_message

    gmail = removal_result_message(ACCOUNT, RemovalResult(revoked=True))
    assert ACCOUNT.email in gmail and "Google" in gmail

    outlook = Account(Provider.OUTLOOK, "ana@outlook.com", id=2)
    url = "https://account.live.com/consent/Manage"
    message = removal_result_message(outlook, RemovalResult(False, url))
    assert text.REVOKE_NOT_SUPPORTED_REASON in message and url in message

    failed = removal_result_message(ACCOUNT, RemovalResult(False, "https://g"))
    assert text.REVOKE_FAILED_REASON in failed and "https://g" in failed


def test_new_password_error():
    """F10-2, F10-5."""
    from exitmap.ui.presenters import new_password_error
    assert new_password_error("", "") == text.PASSWORD_EMPTY
    assert new_password_error("abc", "abd") == text.PASSWORD_MISMATCH
    assert new_password_error("abc", "abc") is None
