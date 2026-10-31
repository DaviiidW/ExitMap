"""Full start with a temporary data directory (spec F2-6, F2-8, F10-1..3; plan §3).

Skipped where Tk has no screen.
"""

import pytest
from fakes import FakeKeyring, FakeMailProvider
from keyring.backends import fail

from exitmap import __main__ as entry
from exitmap.app.analysis import IN_PROGRESS_KEY, analyse, save_analysis
from exitmap.domain.models import Account, Provider
from exitmap.storage.credentials import (
    CREDENTIALS_FILE_NAME,
    EncryptedFileStore,
    KeyringStore,
    MemoryStore,
)
from exitmap.storage.db import Database
from exitmap.ui import dialogs
from exitmap.ui import strings_es as text

GMAIL = "ana.prueba@gmail.com"


@pytest.fixture
def infos(monkeypatch):
    shown = []
    monkeypatch.setattr(dialogs, "show_info", lambda parent, message: shown.append(message))
    return shown


@pytest.fixture
def data_dir(tmp_path):
    with Database(tmp_path / entry.DB_FILE_NAME) as db:
        account = db.add_account(Account(Provider.GMAIL, GMAIL))
        save_analysis(db, account.id, analyse(FakeMailProvider(GMAIL), account_id=account.id))
    return tmp_path


def _close(app):
    app.window.analysis.cancel()
    app.db.close()


def test_saved_list_is_shown_without_analysing_again(tk_root, data_dir, infos):
    """F2-8, F10-1."""
    app = entry.build_app(tk_root, data_dir, FakeKeyring())
    try:
        assert isinstance(app.window.accounts.store, KeyringStore)
        assert app.window.account_list.get(0, "end") == (f"{GMAIL} (Gmail)",)
        assert len(app.window.tree.get_children()) == len(app.db.list_services()) > 0
        assert tk_root.state() == "normal"
        assert infos == []
    finally:
        _close(app)


def test_interrupted_analysis_is_reported_once(tk_root, data_dir, infos):
    """F2-6: the mark left by an analysis that never finished."""
    with Database(data_dir / entry.DB_FILE_NAME) as db:
        db.set_setting(IN_PROGRESS_KEY, "1")
        services = len(db.list_services())

    app = entry.build_app(tk_root, data_dir, FakeKeyring())
    assert infos == [text.ANALYSIS_INTERRUPTED]
    assert len(app.db.list_services()) == services  # last complete analysis kept
    _close(app)

    app = entry.build_app(tk_root, data_dir, FakeKeyring())
    assert infos == [text.ANALYSIS_INTERRUPTED]
    _close(app)


def test_master_password_is_asked_first(tk_root, data_dir, infos, monkeypatch):
    """F10-3."""
    EncryptedFileStore.create(data_dir / CREDENTIALS_FILE_NAME, "clave")
    opened = EncryptedFileStore.open(data_dir / CREDENTIALS_FILE_NAME, "clave")
    asked = []
    monkeypatch.setattr(dialogs.PasswordDialog, "show", lambda self: asked.append(1) or opened)
    app = entry.build_app(tk_root, data_dir, fail.Keyring())
    assert asked == [1] and app.window.accounts.store is opened
    _close(app)


def test_closing_the_password_dialog_does_not_open_the_app(tk_root, data_dir, monkeypatch):
    EncryptedFileStore.create(data_dir / CREDENTIALS_FILE_NAME, "clave")
    monkeypatch.setattr(dialogs.PasswordDialog, "show", lambda self: None)
    assert entry.build_app(tk_root, data_dir, fail.Keyring()) is None


def test_without_keyring_the_choice_waits_for_the_first_connection(tk_root, data_dir, infos):
    """F10-2."""
    app = entry.build_app(tk_root, data_dir, fail.Keyring())
    assert app.window.accounts.store is None
    _close(app)


def test_session_mode_starts_with_memory(tk_root, data_dir, infos):
    """F10-7."""
    from exitmap.storage.credentials import set_session_mode

    with Database(data_dir / entry.DB_FILE_NAME) as db:
        set_session_mode(db, True)
    app = entry.build_app(tk_root, data_dir, FakeKeyring())
    assert isinstance(app.window.accounts.store, MemoryStore)
    _close(app)
