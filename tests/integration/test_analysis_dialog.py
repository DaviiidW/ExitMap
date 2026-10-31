"""Analysis dialog with the fake provider (spec F2-1..6, F2-9, F2-10, F8-1, F8-2).

Skipped where Tk has no screen.
"""

import time
from datetime import UTC, datetime

import pytest
from fakes import ControlledMailProvider, FakeMailProvider

from exitmap.app.accounts import AccountService
from exitmap.app.analysis import AnalysisMode, AnalysisService
from exitmap.app.services import ServiceCatalogue
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import Account, Provider
from exitmap.errors import OfflineError, ReconnectRequiredError
from exitmap.storage.db import Database
from exitmap.ui import strings_es as text
from exitmap.ui.analysis_dialog import AnalysisDialog
from exitmap.ui.main_window import MainWindow
from exitmap.ui.presenters import PeriodChoice

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "exitmap.db"
    with Database(path) as db:
        db.add_account(Account(Provider.GMAIL, GMAIL))
        db.add_account(Account(Provider.OUTLOOK, OUTLOOK))
    return path


@pytest.fixture
def db(db_path):
    with Database(db_path) as db:
        yield db


@pytest.fixture
def analysis(db_path):
    service = AnalysisService(db_path, catalog=load_catalog(CATALOG_PATH))
    yield service
    service.cancel()
    service.join(timeout=5)


def _dialog(tk_root, db, analysis, provider=None, **kwargs):
    providers = []

    def provider_for(account):
        mail = provider or FakeMailProvider(account.email)
        providers.append(mail)
        return mail

    dialog = AnalysisDialog(tk_root, db.list_accounts(), analysis, provider_for, **kwargs)
    return dialog, providers


def _wait(root, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert condition()


def test_defaults(tk_root, db, analysis):
    """F2-1, F2-3: whole mailbox, Spam and Trash off; no re-analysis choice yet."""
    dialog, _ = _dialog(tk_root, db, analysis)
    tk_root.update()
    assert dialog.period.get() == PeriodChoice.WHOLE_MAILBOX
    assert not dialog.include_spam.get() and not dialog.include_trash.get()
    assert set(dialog.period_buttons) == set(PeriodChoice)
    assert str(dialog.start_entry.cget("state")) == "disabled"
    assert dialog.mode_frame.winfo_manager() == ""
    assert dialog.account().email == GMAIL


def test_custom_range_enables_the_dates_and_is_validated(tk_root, db, analysis):
    """F2-2: start after end → it does not start and the reason is shown."""
    dialog, providers = _dialog(tk_root, db, analysis)
    dialog.period_buttons[PeriodChoice.CUSTOM].invoke()
    assert str(dialog.start_entry.cget("state")) == "normal"
    dialog.start_text.set("02/01/2025")
    dialog.end_text.set("01/01/2025")
    dialog.start()
    assert "posterior" in dialog.error.cget("text")
    assert not analysis.running and providers == [] and not dialog.running

    dialog.start_text.set("1/1/25x")
    dialog.start()
    assert "DD/MM/AAAA" in dialog.error.cget("text")


def test_complete_analysis_shows_the_result(tk_root, db, analysis):
    """F2-4, F2-7: progress n of total, then the number of services."""
    dialog, _ = _dialog(tk_root, db, analysis)
    dialog.start()
    assert dialog.running
    _wait(tk_root, lambda: not dialog.running)
    done, total = dialog.progress_label.cget("text").split(" de ")
    assert done == total
    count = len(db.list_services())
    assert count > 0
    assert dialog.result.cget("text") == text.ANALYSIS_DONE_MANY.format(count=count)
    assert dialog.progress_button.cget("text") == text.CLOSE


def test_empty_result_suggests_wider_period(tk_root, db, analysis):
    """F2-10."""
    dialog, _ = _dialog(tk_root, db, analysis)
    dialog.period_buttons[PeriodChoice.CUSTOM].invoke()
    dialog.start_text.set("01/01/1990")
    dialog.end_text.set("31/12/1990")
    dialog.start()
    _wait(tk_root, lambda: not dialog.running)
    assert dialog.result.cget("text") == text.NO_SERVICES_FOUND


def test_progress_and_cancel_keep_the_previous_results(tk_root, db, analysis):
    """F2-4, F2-5."""
    provider = ControlledMailProvider(GMAIL, pause_at=2)
    dialog, _ = _dialog(tk_root, db, analysis, provider)
    dialog.start()
    assert provider.paused.wait(5)
    total = len(provider.list_message_ids(*_whole()))
    _wait(tk_root, lambda: dialog.progress_label.cget("text") == f"1 de {total}")
    dialog.close()  # closing the window cancels
    provider.resume.set()
    _wait(tk_root, lambda: not dialog.running)
    assert dialog.result.cget("text") == text.ANALYSIS_CANCELLED
    assert db.list_services() == []


def test_failure_says_it_must_start_again(tk_root, db, analysis):
    """F2-6."""
    provider = ControlledMailProvider(GMAIL, fail_at=1, error=OfflineError())
    dialog, _ = _dialog(tk_root, db, analysis, provider)
    dialog.start()
    _wait(tk_root, lambda: not dialog.running)
    message = dialog.result.cget("text")
    assert OfflineError().user_message in message and text.ANALYSIS_STOPPED in message


def test_account_without_access_asks_to_reconnect(tk_root, db, analysis):
    def provider_for(account):
        raise ReconnectRequiredError()

    dialog = AnalysisDialog(tk_root, db.list_accounts(), analysis, provider_for)
    dialog.start()
    assert dialog.error.cget("text") == ReconnectRequiredError().user_message
    assert not analysis.running


def test_reanalysis_offers_the_mode_and_says_states_are_kept(tk_root, db, analysis):
    """F8-1, F8-2."""
    outlook = db.list_accounts()[1]
    db.set_last_complete_analysis(outlook.id, datetime(2025, 1, 1, tzinfo=UTC))
    dialog, _ = _dialog(tk_root, db, analysis, selected=db.list_accounts()[1])
    tk_root.update()
    assert dialog.mode_frame.winfo_manager() == "grid"
    assert dialog.notice.cget("text") == text.REANALYSIS_NOTICE
    assert dialog.mode.get() == AnalysisMode.ALL
    dialog.mode_buttons[AnalysisMode.NEW_ONLY].invoke()
    assert str(dialog.period_buttons[PeriodChoice.LAST_YEAR].cget("state")) == "disabled"
    assert dialog.options().mode is AnalysisMode.NEW_ONLY

    dialog.account_box.current(0)  # Gmail has no previous analysis
    dialog.account_box.event_generate("<<ComboboxSelected>>")
    tk_root.update()
    assert dialog.mode_frame.winfo_manager() == ""
    assert dialog.mode.get() == AnalysisMode.ALL


def test_main_window_allows_one_analysis_at_a_time(tk_root, db, analysis, monkeypatch):
    """F2-9."""
    provider = ControlledMailProvider(GMAIL, pause_at=1)
    accounts = AccountService(db, None)
    monkeypatch.setattr(accounts, "provider_for", lambda account: provider)
    window = MainWindow(tk_root, accounts, ServiceCatalogue(db), analysis=analysis)
    assert str(window.analyse_button.cget("state")) == "normal"

    window.analyse()
    window.analysis_dialog.start()
    assert provider.paused.wait(5)
    assert str(window.analyse_button.cget("state")) == "disabled"
    assert window.analysis_status.cget("text") == text.ANALYSIS_RUNNING
    first = window.analysis_dialog
    window.analyse()
    assert window.analysis_dialog is first

    provider.resume.set()
    dialog = window.analysis_dialog
    _wait(tk_root, lambda: not dialog.running)
    assert str(window.analyse_button.cget("state")) == "normal"
    assert window.analysis_status.cget("text") == ""
    assert window.tree.get_children()  # the list shows the new services


def test_analyse_is_disabled_without_accounts(tk_root, tmp_path, analysis):
    with Database(tmp_path / "empty.db") as db:
        window = MainWindow(tk_root, AccountService(db, None), ServiceCatalogue(db),
                            analysis=analysis)
        assert str(window.analyse_button.cget("state")) == "disabled"
        window.analyse()
        assert window.analysis_dialog is None


def _whole():
    from exitmap.providers.base import Folders, Period
    return Period(), Folders()
