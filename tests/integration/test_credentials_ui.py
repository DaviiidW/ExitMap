"""Credentials and settings from the interface, with the keyring simulated as missing
(spec F10-2..7). Skipped where Tk has no screen."""

import time

import pytest
from fakes import FakeKeyring, FakeProviderFactory
from keyring.backends import fail

from exitmap.app.accounts import AccountService, Registration, tokens_key
from exitmap.app.services import ServiceCatalogue
from exitmap.domain.models import Account, Provider, Service, State
from exitmap.errors import ReconnectRequiredError
from exitmap.storage.credentials import (
    CREDENTIALS_FILE_NAME,
    EncryptedFileStore,
    KeyringStore,
    MemoryStore,
    StoreNeed,
    choose_store,
    session_mode,
)
from exitmap.storage.db import Database
from exitmap.ui import dialogs
from exitmap.ui import strings_es as text
from exitmap.ui.dialogs import (
    ConnectFlow,
    PasswordDialog,
    SettingsDialog,
    StoreChoiceDialog,
    background_connect,
)
from exitmap.ui.main_window import MainWindow

GMAIL = "ana.prueba@gmail.com"
REG = Registration("id", "secret")
NO_KEYRING = fail.Keyring()


class Prompts:
    def __init__(self):
        self.answer = True
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
def db_path(tmp_path):
    return tmp_path / "exitmap.db"


@pytest.fixture
def db(db_path):
    with Database(db_path) as db:
        yield db


def _wait(root, flow, timeout=5):
    deadline = time.monotonic() + timeout
    root.update()
    while flow.waiting is not None and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert flow.waiting is None


def test_store_choice_validates_the_new_password(tk_root):
    """F10-2."""
    dialog = StoreChoiceDialog(tk_root)
    dialog.accept()
    assert dialog.error.cget("text") == text.PASSWORD_EMPTY
    dialog.password.set("clave")
    dialog.repeat.set("otra")
    dialog.accept()
    assert dialog.error.cget("text") == text.PASSWORD_MISMATCH
    dialog.repeat.set("clave")
    dialog.accept()
    assert dialog.result == ("password", "clave")


def test_store_choice_session(tk_root):
    dialog = StoreChoiceDialog(tk_root)
    dialog.session_option.invoke()
    assert str(dialog.password_entry.cget("state")) == "disabled"
    dialog.accept()
    assert dialog.result == ("session", None)


@pytest.mark.parametrize("choice", [("password", "clave"), ("session", None)])
def test_first_connection_without_keyring_asks_the_choice(tk_root, tmp_path, db, db_path,
                                                          monkeypatch, choice):
    """F10-2: the choice comes before connecting; session mode stays as the setting."""
    assert choose_store(db, tmp_path, NO_KEYRING).need is StoreNeed.CHOICE
    monkeypatch.setattr(StoreChoiceDialog, "show", lambda self: choice)
    accounts = AccountService(db, None, FakeProviderFactory(GMAIL))
    window = MainWindow(tk_root, accounts, ServiceCatalogue(db),
                        connect_runner=background_connect(accounts, db_path), data_dir=tmp_path)
    flow = window.connect_flow
    flow.ask_provider = lambda: Provider.GMAIL
    flow.ask_registration = lambda provider, error: REG
    flow.start()
    _wait(tk_root, flow)

    assert [a.email for a in db.list_accounts()] == [GMAIL]
    if choice[0] == "password":
        assert isinstance(accounts.store, EncryptedFileStore)
        assert choose_store(db, tmp_path, NO_KEYRING).need is StoreNeed.PASSWORD
    else:
        assert isinstance(accounts.store, MemoryStore) and session_mode(db)
        assert not (tmp_path / CREDENTIALS_FILE_NAME).exists()
        assert choose_store(db, tmp_path, NO_KEYRING).need is StoreNeed.NOTHING


def test_cancelled_choice_connects_nothing(tk_root, tmp_path, db, db_path):
    factory = FakeProviderFactory(GMAIL)
    accounts = AccountService(db, None, factory)
    asked = []
    flow = ConnectFlow(tk_root, accounts, background_connect(accounts, db_path), None,
                       lambda: None, ask_provider=lambda: asked.append(1),
                       choose_store=lambda: None)
    flow.start()
    assert asked == [] and accounts.store is None and factory.built == []


@pytest.fixture
def locked(tmp_path):
    store = EncryptedFileStore.create(tmp_path / CREDENTIALS_FILE_NAME, "clave")
    store.set(tokens_key(Provider.GMAIL, GMAIL), "{}")
    return tmp_path


def test_password_is_asked_and_can_be_retried(tk_root, locked):
    """F10-3, F10-4."""
    dialog = PasswordDialog(tk_root, locked)
    dialog.password.set("mala")
    dialog.accept()
    assert dialog.error.cget("text").startswith(text.ERRORS["wrong_password"][0])
    assert dialog.password.get() == "" and dialog.winfo_exists()
    dialog.password.set("clave")
    dialog.accept()
    assert dialog.result.get(tokens_key(Provider.GMAIL, GMAIL)) == "{}"


def test_damaged_file_is_a_wrong_password(tk_root, locked):
    (locked / CREDENTIALS_FILE_NAME).write_text("dañado", encoding="utf-8")
    dialog = PasswordDialog(tk_root, locked)
    dialog.password.set("clave")
    dialog.accept()
    assert dialog.error.cget("text").startswith(text.ERRORS["wrong_password"][0])


def test_reset_needs_confirmation(tk_root, locked, prompts):
    prompts.answer = False
    dialog = PasswordDialog(tk_root, locked)
    dialog.forgot_button.invoke()
    assert (locked / CREDENTIALS_FILE_NAME).exists() and not dialog.creating


def test_reset_deletes_credentials_and_keeps_results(tk_root, locked, prompts):
    """F10-5."""
    with Database(locked / "exitmap.db") as db:
        account = db.add_account(Account(Provider.GMAIL, GMAIL))
        service = db.save_service(Service(account_id=account.id, domain="x.es", name="X"))
        db.set_state(service.id, State.KEEP)

    dialog = PasswordDialog(tk_root, locked)
    dialog.forgot()
    assert dialog.creating and prompts.confirms == [text.RESET_CONFIRM]
    assert not (locked / CREDENTIALS_FILE_NAME).exists()
    dialog.password.set("nueva")
    dialog.repeat.set("otra")
    dialog.accept()
    assert dialog.error.cget("text") == text.PASSWORD_MISMATCH
    dialog.repeat.set("nueva")
    dialog.accept()
    store = dialog.result
    assert store.get(tokens_key(Provider.GMAIL, GMAIL)) is None
    assert EncryptedFileStore.open(locked / CREDENTIALS_FILE_NAME, "nueva").get("x") is None

    with Database(locked / "exitmap.db") as db:
        assert db.get_service(service.id).state is State.KEEP
        with pytest.raises(ReconnectRequiredError):  # the account must be reconnected
            AccountService(db, store).provider_for(db.list_accounts()[0])


def _connected(db, store):
    accounts = AccountService(db, store, FakeProviderFactory(GMAIL))
    accounts.connect(Provider.GMAIL, REG)
    return accounts


def test_session_mode_on_deletes_saved_credentials(tk_root, tmp_path, db, prompts):
    """F10-6: keyring credentials deleted; the account stays but must be reconnected."""
    keyring = FakeKeyring()
    accounts = _connected(db, KeyringStore(keyring))
    assert keyring.passwords
    dialog = SettingsDialog(tk_root, accounts, tmp_path)
    assert not dialog.session.get()
    dialog.session_check.invoke()

    assert session_mode(db) and isinstance(accounts.store, MemoryStore)
    assert keyring.passwords == {}
    assert [a.email for a in db.list_accounts()] == [GMAIL]
    assert prompts.infos == [text.SESSION_ON_DONE]
    with pytest.raises(ReconnectRequiredError):
        accounts.provider_for(db.list_accounts()[0])


def test_session_mode_on_removes_the_encrypted_file(tk_root, tmp_path, db, prompts):
    store = EncryptedFileStore.create(tmp_path / CREDENTIALS_FILE_NAME, "clave")
    accounts = _connected(db, store)
    SettingsDialog(tk_root, accounts, tmp_path).session_check.invoke()
    assert not (tmp_path / CREDENTIALS_FILE_NAME).exists()


def test_session_mode_needs_confirmation(tk_root, tmp_path, db, prompts):
    prompts.answer = False
    keyring = FakeKeyring()
    accounts = _connected(db, KeyringStore(keyring))
    dialog = SettingsDialog(tk_root, accounts, tmp_path)
    dialog.session_check.invoke()
    assert not dialog.session.get() and not session_mode(db) and keyring.passwords


def test_locked_keyring_keeps_session_mode_off(tk_root, tmp_path, db, prompts):
    keyring = FakeKeyring()
    accounts = _connected(db, KeyringStore(keyring))
    keyring.fail = True
    dialog = SettingsDialog(tk_root, accounts, tmp_path)
    dialog.session_check.invoke()
    assert not dialog.session.get() and not session_mode(db)
    assert len(prompts.errors) == 1


def test_session_mode_off(tk_root, tmp_path, db, prompts):
    """F10-7 until it is turned off; off takes effect on the next start."""
    accounts = AccountService(db, MemoryStore())
    from exitmap.storage.credentials import set_session_mode
    set_session_mode(db, True)
    dialog = SettingsDialog(tk_root, accounts, tmp_path)
    assert dialog.session.get()
    dialog.session_check.invoke()
    assert not session_mode(db)
    assert prompts.infos == [text.SESSION_OFF_DONE]


def test_settings_button(tk_root, tmp_path, db, monkeypatch):
    opened = []
    monkeypatch.setattr(SettingsDialog, "show", lambda self: opened.append(self))
    window = MainWindow(tk_root, AccountService(db, MemoryStore()), ServiceCatalogue(db),
                        data_dir=tmp_path)
    window.settings_button.invoke()
    assert len(opened) == 1
    without = MainWindow(tk_root, AccountService(db, MemoryStore()), ServiceCatalogue(db))
    assert str(without.settings_button.cget("state")) == "disabled"


def test_without_store_an_account_is_removed_and_must_be_reconnected(db):
    """No keyring and no choice yet (session mode turned off): no credentials to touch."""
    account = db.add_account(Account(Provider.GMAIL, GMAIL))
    accounts = AccountService(db, None)
    with pytest.raises(ReconnectRequiredError):
        accounts.provider_for(account)
    result = accounts.remove(account.id)
    assert not result.revoked and result.manual_revoke_url
    assert db.list_accounts() == []
