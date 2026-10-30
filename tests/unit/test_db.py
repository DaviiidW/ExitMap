from datetime import datetime, timezone

import pytest

from exitmap.domain.models import Account, Provider
from exitmap.errors import AccountAlreadyConnectedError
from exitmap.storage.db import Database


@pytest.fixture
def db():
    with Database(":memory:") as database:
        yield database


def _tables(db):
    rows = db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_schema_has_all_tables(db):
    assert _tables(db) == {"accounts", "services", "evidence", "settings"}


def test_foreign_keys_are_enabled(db):
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_add_account_sets_id_and_created_at(db):
    account = db.add_account(Account(Provider.GMAIL, "ana@example.com"))

    assert account.id is not None
    assert account.created_at is not None


def test_account_fields_round_trip(db):
    analysed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    db.add_account(
        Account(Provider.OUTLOOK, "ana@example.com", "ref-1", last_complete_analysis_at=analysed)
    )

    [account] = db.list_accounts()

    assert account.provider is Provider.OUTLOOK
    assert account.email == "ana@example.com"
    assert account.client_registration_ref == "ref-1"
    assert account.last_complete_analysis_at == analysed


def test_same_email_with_another_provider_is_allowed(db):
    db.add_account(Account(Provider.GMAIL, "ana@example.com"))
    db.add_account(Account(Provider.OUTLOOK, "ana@example.com"))

    assert len(db.list_accounts()) == 2


def test_duplicate_account_raises_understandable_error(db):
    db.add_account(Account(Provider.GMAIL, "ana@example.com"))

    with pytest.raises(AccountAlreadyConnectedError):
        db.add_account(Account(Provider.GMAIL, "ana@example.com"))
