"""Removing an account from the interface (spec F9-1..4). Skipped where Tk has no screen."""

import time

import pytest
from fakes import FakeKeyring, FakeMailProvider, FakeProviderFactory

from exitmap.app.accounts import AccountService, Registration
from exitmap.app.analysis import analyse, save_analysis
from exitmap.app.services import ServiceCatalogue
from exitmap.domain.models import Provider
from exitmap.errors import KeyringUnavailableError
from exitmap.providers.gmail import PERMISSIONS_URL as GOOGLE_URL
from exitmap.providers.outlook import PERMISSIONS_URL as MICROSOFT_URL
from exitmap.storage.credentials import KeyringStore
from exitmap.storage.db import Database
from exitmap.ui import dialogs
from exitmap.ui import strings_es as text
from exitmap.ui.dialogs import background_remove
from exitmap.ui.main_window import MainWindow

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"


class Prompts:
    def __init__(self):
        self.answer = False
        self.confirms, self.infos, self.errors = [], [], []


@pytest.fixture
def prompts(monkeypatch):
    shown = Prompts()

    def confirm(parent, message):
        shown.confirms.append(message)
        return shown.answer

    monkeypatch.setattr(dialogs, "confirm", confirm)
    monkeypatch.setattr(dialogs, "show_info", lambda p, m: shown.infos.append(m))
    monkeypatch.setattr(dialogs, "show_error", lambda p, e: shown.errors.append(e))
    return shown


@pytest.fixture
def setup(tk_root, tmp_path):
    path = tmp_path / "exitmap.db"
    db = Database(path)
    keyring = FakeKeyring()
    factory = FakeProviderFactory()
    accounts = AccountService(db, KeyringStore(keyring), factory)
    for provider, email, registration in (
        (Provider.GMAIL, GMAIL, Registration("id", "secret")),
        (Provider.OUTLOOK, OUTLOOK, Registration("ms-id")),
    ):
        factory.next_email = email
        account = accounts.connect(provider, registration).account
        save_analysis(db, account.id, analyse(FakeMailProvider(email), account_id=account.id))
    window = MainWindow(tk_root, accounts, ServiceCatalogue(db),
                        remove_runner=background_remove(accounts, path))
    yield window, db, keyring, factory
    db.close()


def _select(window, email):
    labels = window.account_list.get(0, "end")
    index = next(i for i, label in enumerate(labels) if label.startswith(email))
    window.account_list.selection_clear(0, "end")
    window.account_list.selection_set(index)
    window._update_remove_button()


def _wait(root, flow, timeout=5):
    deadline = time.monotonic() + timeout
    root.update()
    while flow.waiting is not None and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert flow.waiting is None


def test_button_needs_a_selected_account(setup):
    window, *_ = setup
    assert str(window.remove_button.cget("state")) == "disabled"
    _select(window, GMAIL)
    assert str(window.remove_button.cget("state")) == "normal"


def test_cancelling_the_confirmation_deletes_nothing(tk_root, setup, prompts):
    """F9-1."""
    window, db, *_ = setup
    _select(window, GMAIL)
    window.remove_button.invoke()
    message = prompts.confirms[0]
    assert GMAIL in message and "credenciales" in message and "servicios" in message
    assert window.remove_flow.waiting is None
    assert len(db.list_accounts()) == 2


def test_gmail_is_removed_and_its_permission_withdrawn(tk_root, setup, prompts):
    """F9-2, F9-3."""
    window, db, keyring, factory = setup
    factory.next_email = GMAIL  # the fake mailbox decides the provider of the fake
    prompts.answer = True
    _select(window, GMAIL)
    window.remove_account()
    _wait(tk_root, window.remove_flow)
    assert [a.email for a in db.list_accounts()] == [OUTLOOK]
    assert window.account_list.get(0, "end") == (f"{OUTLOOK} (Outlook)",)
    assert all(window.tree.set(i, "account") == OUTLOOK for i in window.tree.get_children())
    assert factory.last.revoked
    assert prompts.infos == [text.REMOVED_AND_REVOKED.format(account=GMAIL)]


def test_outlook_says_where_to_withdraw_the_permission(tk_root, setup, prompts):
    """F9-4."""
    window, db, *_ = setup
    prompts.answer = True
    _select(window, OUTLOOK)
    window.remove_account()
    _wait(tk_root, window.remove_flow)
    assert [a.email for a in db.list_accounts()] == [GMAIL]
    assert MICROSOFT_URL in prompts.infos[0]


def test_gmail_without_network_still_deletes_and_explains(tk_root, setup, prompts):
    """F9-4."""
    from exitmap.errors import OfflineError

    window, db, keyring, factory = setup
    factory.next_email = GMAIL
    factory.revoke_error = OfflineError()
    prompts.answer = True
    _select(window, GMAIL)
    window.remove_account()
    _wait(tk_root, window.remove_flow)
    assert [a.email for a in db.list_accounts()] == [OUTLOOK]
    assert GOOGLE_URL in prompts.infos[0]


def test_locked_keyring_keeps_the_account(tk_root, setup, prompts):
    window, db, keyring, _ = setup
    keyring.fail = True
    prompts.answer = True
    _select(window, GMAIL)
    window.remove_account()
    _wait(tk_root, window.remove_flow)
    assert len(db.list_accounts()) == 2
    assert [type(e) for e in prompts.errors] == [KeyringUnavailableError]
