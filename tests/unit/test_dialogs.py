"""Helpers of the dialogs that need no screen (spec F1, constitution 5 and 6)."""

import logging

from fakes import FakeProviderFactory

from exitmap.app.accounts import AccountService, Registration
from exitmap.domain.models import Provider
from exitmap.errors import ExitMapError, OfflineError
from exitmap.storage.credentials import MemoryStore
from exitmap.storage.db import Database
from exitmap.ui.dialogs import GUIDE_PATH, background_connect, user_error


def test_user_error_keeps_app_errors():
    error = OfflineError()
    assert user_error(error) is error


def test_unexpected_error_becomes_generic_and_only_its_type_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="exitmap"):
        error = user_error(ValueError("token ya29.secret"))
    assert type(error) is ExitMapError
    assert "ValueError" in caplog.text and "ya29" not in caplog.text


def test_guide_is_in_the_docs_folder():
    assert GUIDE_PATH.parts[-2:] == ("docs", "guia-registro.md")


def test_background_connect_uses_its_own_connection(tmp_path):
    path = tmp_path / "exitmap.db"
    with Database(path) as db:
        accounts = AccountService(db, MemoryStore(), FakeProviderFactory())
        result = background_connect(accounts, path)(Provider.GMAIL, Registration("id", "secret"))
        assert [a.email for a in db.list_accounts()] == [result.account.email]
        assert not accounts.needs_registration(Provider.GMAIL)
