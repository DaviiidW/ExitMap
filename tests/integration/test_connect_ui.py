"""Connecting an account from the interface with the fake provider
(spec F1-1, F1-2, F1-3, F1-5, F1-6, F1-7). Skipped where Tk has no screen."""

import time

import pytest
from fakes import FakeOpener, FakeProviderFactory

from exitmap.app.accounts import AccountService, Registration
from exitmap.app.services import ServiceCatalogue
from exitmap.domain.models import Provider
from exitmap.errors import AuthorizationDeniedError, InvalidRegistrationError
from exitmap.storage.credentials import MemoryStore
from exitmap.storage.db import Database
from exitmap.ui import dialogs
from exitmap.ui import strings_es as text
from exitmap.ui.dialogs import (
    GUIDE_PATH,
    ConnectFlow,
    ProviderDialog,
    RegistrationDialog,
    background_connect,
)
from exitmap.ui.main_window import MainWindow

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"
GOOGLE_REG = Registration("123.apps.googleusercontent.com", "GOCSPX-secret")


class Messages:
    def __init__(self):
        self.errors = []
        self.infos = []


@pytest.fixture
def messages(monkeypatch):
    shown = Messages()
    monkeypatch.setattr(dialogs, "show_error", lambda parent, error: shown.errors.append(error))
    monkeypatch.setattr(dialogs, "show_info", lambda parent, message: shown.infos.append(message))
    return shown


@pytest.fixture
def setup(tk_root, tmp_path):
    path = tmp_path / "exitmap.db"
    db = Database(path)
    factory = FakeProviderFactory(GMAIL)
    accounts = AccountService(db, MemoryStore(), factory)
    window = MainWindow(tk_root, accounts, ServiceCatalogue(db),
                        connect_runner=background_connect(accounts, path), opener=FakeOpener())
    yield window, accounts, factory, path
    db.close()


def _flow(window, accounts, path, provider, registrations):
    asked = []

    def ask_registration(p, error):
        asked.append((p, error))
        return registrations.pop(0) if registrations else None

    flow = ConnectFlow(window, accounts, background_connect(accounts, path), FakeOpener(),
                       window.refresh, ask_provider=lambda: provider,
                       ask_registration=ask_registration)
    return flow, asked


def _wait(root, flow, timeout=5):
    deadline = time.monotonic() + timeout
    root.update()
    while flow.waiting is not None and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert flow.waiting is None


def test_provider_dialog_offers_gmail_and_outlook(tk_root):
    """F1-1."""
    dialog = ProviderDialog(tk_root)
    assert set(dialog.buttons) == {Provider.GMAIL, Provider.OUTLOOK}
    dialog.buttons[Provider.OUTLOOK].invoke()
    assert dialog.result is Provider.OUTLOOK


def test_registration_dialog_links_to_the_guide(tk_root):
    """F1-2: Google asks for ID and secret, the guide opens, the error is explained."""
    opener = FakeOpener()
    dialog = RegistrationDialog(tk_root, Provider.GMAIL, opener, error="Datos mal")
    dialog.guide.invoke()
    assert opener.urls == [GUIDE_PATH.as_uri()]
    assert dialog.error.cget("text") == "Datos mal"
    dialog.client_id.set(GOOGLE_REG.client_id)
    dialog.client_secret.set(GOOGLE_REG.client_secret)
    dialog.accept()
    assert dialog.result == GOOGLE_REG


def test_microsoft_registration_has_no_secret(tk_root):
    dialog = RegistrationDialog(tk_root, Provider.OUTLOOK, FakeOpener())
    dialog.client_id.set("abc")
    dialog.client_secret.set("ignored")
    dialog.accept()
    assert dialog.result == Registration("abc", None)


def test_first_connection_asks_registration_and_shows_the_account(tk_root, setup, messages):
    """F1-2, F1-3, F1-5."""
    window, accounts, factory, path = setup
    flow, asked = _flow(window, accounts, path, Provider.GMAIL, [GOOGLE_REG])
    flow.start()
    assert isinstance(flow.waiting, dialogs.WaitDialog)
    _wait(tk_root, flow)
    assert asked == [(Provider.GMAIL, None)]
    assert window.account_list.get(0, "end") == (f"{GMAIL} (Gmail)",)

    factory.next_email = OUTLOOK
    flow, asked = _flow(window, accounts, path, Provider.OUTLOOK, [Registration("ms-id")])
    flow.start()
    _wait(tk_root, flow)
    assert window.account_list.get(0, "end") == (f"{GMAIL} (Gmail)", f"{OUTLOOK} (Outlook)")
    assert messages.errors == [] and messages.infos == []


def test_saved_registration_is_not_asked_again(tk_root, setup, messages):
    window, accounts, factory, path = setup
    flow, _ = _flow(window, accounts, path, Provider.GMAIL, [GOOGLE_REG])
    flow.start()
    _wait(tk_root, flow)
    factory.next_email = OUTLOOK  # a second account with the saved Google registration
    flow, asked = _flow(window, accounts, path, Provider.GMAIL, [])
    flow.start()
    _wait(tk_root, flow)
    assert asked == []
    assert window.account_list.size() == 2


def test_wrong_registration_is_explained_and_asked_again(tk_root, setup, messages):
    """F1-2."""
    window, accounts, factory, path = setup
    flow, asked = _flow(window, accounts, path, Provider.GMAIL,
                        [Registration("", ""), GOOGLE_REG])
    flow.start()
    _wait(tk_root, flow)
    _wait(tk_root, flow)
    assert asked == [(Provider.GMAIL, None),
                     (Provider.GMAIL, InvalidRegistrationError().user_message)]
    assert window.account_list.size() == 1


def test_denied_authorization_adds_nothing_and_explains(tk_root, setup, messages):
    """F1-6."""
    window, accounts, factory, path = setup
    factory.authorize_error = AuthorizationDeniedError()
    flow, _ = _flow(window, accounts, path, Provider.GMAIL, [GOOGLE_REG])
    flow.start()
    _wait(tk_root, flow)
    assert [type(e) for e in messages.errors] == [AuthorizationDeniedError]
    assert window.account_list.size() == 0


def test_account_already_connected_is_reported(tk_root, setup, messages):
    """F1-7."""
    window, accounts, factory, path = setup
    for _ in range(2):
        flow, _ = _flow(window, accounts, path, Provider.GMAIL, [GOOGLE_REG])
        flow.start()
        _wait(tk_root, flow)
    assert window.account_list.size() == 1
    assert messages.infos == [text.ERRORS["account_already_connected"][0]]


def test_cancelling_adds_nothing(tk_root, setup, messages):
    window, accounts, factory, path = setup
    _flow(window, accounts, path, None, [])[0].start()
    flow, _ = _flow(window, accounts, path, Provider.GMAIL, [])
    flow.start()
    assert flow.waiting is None and factory.built == []


def test_main_window_connect_button(tk_root, setup):
    window, *_ = setup
    assert str(window.connect_button.cget("state")) == "normal"
    window.connect_flow.ask_provider = lambda: None
    window.connect_button.invoke()
