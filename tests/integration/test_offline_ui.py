"""No connection notice and reconnecting an account whose permission expired
(spec §5; plan §4). Skipped where Tk has no screen."""

import time

import pytest
from fakes import ControlledMailProvider, FakeMailProvider, FakeOpener, FakeProviderFactory

from exitmap.app.accounts import AccountService, Registration
from exitmap.app.analysis import AnalysisService, analyse, save_analysis
from exitmap.app.services import ServiceCatalogue
from exitmap.app.unsubscribe import UnsubscribeService
from exitmap.domain.models import Provider, State
from exitmap.errors import OfflineError, PermissionExpiredError, ReconnectRequiredError
from exitmap.storage.credentials import MemoryStore
from exitmap.storage.db import Database
from exitmap.ui import dialogs
from exitmap.ui import strings_es as text
from exitmap.ui.dialogs import background_connect, background_remove
from exitmap.ui.main_window import MainWindow

GMAIL = "ana.prueba@gmail.com"


class FakeHttp:
    def __init__(self):
        self.error = None

    def post_form(self, url, form):
        if self.error:
            raise self.error
        return 200


@pytest.fixture(autouse=True)
def prompts(monkeypatch):
    shown = {"infos": [], "errors": []}
    monkeypatch.setattr(dialogs, "confirm", lambda parent, message: True)
    monkeypatch.setattr(dialogs, "show_info", lambda p, m: shown["infos"].append(m))
    monkeypatch.setattr(dialogs, "show_error", lambda p, e: shown["errors"].append(e))
    return shown


@pytest.fixture
def setup(tk_root, tmp_path):
    path = tmp_path / "exitmap.db"
    db = Database(path)
    factory = FakeProviderFactory(GMAIL)
    accounts = AccountService(db, MemoryStore(), factory)
    account = accounts.connect(Provider.GMAIL, Registration("id", "secret")).account
    save_analysis(db, account.id, analyse(FakeMailProvider(GMAIL), account_id=account.id))
    http = FakeHttp()
    analysis = AnalysisService(path)
    window = MainWindow(
        tk_root, accounts, ServiceCatalogue(db, FakeOpener()),
        connect_runner=background_connect(accounts, path), opener=FakeOpener(),
        analysis=analysis, unsubscribe=UnsubscribeService(db, http, FakeOpener()),
        remove_runner=background_remove(accounts, path),
    )
    yield window, db, accounts, factory, http, analysis
    analysis.cancel()
    analysis.join(5)
    db.close()


def _wait(root, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert condition()


def _analyse(tk_root, window, accounts, monkeypatch, provider):
    monkeypatch.setattr(accounts, "provider_for", lambda account: provider)
    window.analyse()
    dialog = window.analysis_dialog
    dialog.start()
    _wait(tk_root, lambda: not dialog.running)
    return dialog


def test_analysis_without_network_shows_the_notice_until_one_works(tk_root, setup, monkeypatch):
    window, db, accounts, *_ = setup
    assert window.offline_notice.winfo_manager() == ""
    dialog = _analyse(tk_root, window, accounts, monkeypatch,
                      ControlledMailProvider(GMAIL, fail_at=1, error=OfflineError()))
    assert window.offline_notice.winfo_manager() == "grid"
    assert window.offline_notice.cget("text") == text.OFFLINE_NOTICE
    assert str(window.analyse_button.cget("state")) == "normal"  # still available
    dialog.destroy()

    _analyse(tk_root, window, accounts, monkeypatch, FakeMailProvider(GMAIL))
    assert window.offline_notice.winfo_manager() == ""


def test_automatic_unsubscribe_without_network_shows_the_notice(tk_root, setup):
    window, db, accounts, factory, http, _ = setup
    http.error = OfflineError()
    spotify = next(s for s in db.list_services() if s.domain == "spotify.com")
    window.tree.selection_set(str(spotify.id))
    page = window.open_selected_service()
    page.unsubscribe()
    assert window.offline_notice.winfo_manager() == "grid"
    assert db.get_service(spotify.id).state is State.PENDING

    http.error = None
    page.unsubscribe()
    assert window.offline_notice.winfo_manager() == ""


def test_web_unsubscribe_does_not_touch_the_notice(tk_root, setup):
    window, db, *_ = setup
    window.report_network(OfflineError())
    amazon = next(s for s in db.list_services() if s.domain == "amazon.es")
    window.tree.selection_set(str(amazon.id))
    window.open_selected_service().unsubscribe()
    assert window.offline_notice.winfo_manager() == "grid"


def test_connecting_without_network_shows_the_notice(tk_root, setup):
    window, db, accounts, factory, *_ = setup
    factory.authorize_error = OfflineError()
    window.connect_flow.start(Provider.GMAIL)
    _wait(tk_root, lambda: window.connect_flow.waiting is None)
    assert window.offline_notice.winfo_manager() == "grid"


def test_removing_with_revocation_clears_the_notice(tk_root, setup):
    window, db, *_ = setup
    window.report_network(OfflineError())
    window.account_list.selection_set(0)
    window.remove_account()
    _wait(tk_root, lambda: window.remove_flow.waiting is None)
    assert db.list_accounts() == []
    assert window.offline_notice.winfo_manager() == ""


def test_expired_permission_names_the_account_and_offers_to_reconnect(tk_root, setup,
                                                                      monkeypatch):
    """Spec §5: results and states stay; reconnecting renews the access (F1-7)."""
    window, db, accounts, factory, *_ = setup
    services_before = len(db.list_services())
    dialog = _analyse(tk_root, window, accounts, monkeypatch,
                      ControlledMailProvider(GMAIL, fail_at=1, error=PermissionExpiredError()))
    message = dialog.result.cget("text")
    assert PermissionExpiredError().user_message in message and GMAIL in message
    assert dialog.progress_reconnect.winfo_manager() == "pack"
    assert window.offline_notice.winfo_manager() == ""

    started = []
    monkeypatch.setattr(window.connect_flow, "start", lambda provider=None: started.append(
        provider))
    dialog.progress_reconnect.invoke()
    assert started == [Provider.GMAIL]
    assert len(db.list_services()) == services_before


def test_account_without_saved_access_offers_to_reconnect(tk_root, setup, monkeypatch):
    window, db, accounts, *_ = setup

    def no_access(account):
        raise ReconnectRequiredError()

    monkeypatch.setattr(accounts, "provider_for", no_access)
    window.analyse()
    dialog = window.analysis_dialog
    dialog.start()
    assert GMAIL in dialog.error.cget("text")
    assert dialog.options_reconnect.winfo_manager() == "pack"
    started = []
    monkeypatch.setattr(window.connect_flow, "start", lambda provider=None: started.append(
        provider))
    dialog.options_reconnect.invoke()
    assert started == [Provider.GMAIL]


def test_reconnect_renews_the_access_without_asking_the_provider(tk_root, setup, prompts):
    """F1-7: the same account connected again is not duplicated."""
    window, db, accounts, factory, *_ = setup
    asked = []
    window.connect_flow.ask_provider = lambda: asked.append(1)
    window.reconnect(db.list_accounts()[0])
    _wait(tk_root, lambda: window.connect_flow.waiting is None)
    assert asked == [] and len(db.list_accounts()) == 1
    assert prompts["infos"] == [text.ERRORS["account_already_connected"][0]]
