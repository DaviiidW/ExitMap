import stat
import sys

import pytest

from exitmap.domain.models import Account, Provider
from exitmap.errors import AccountAlreadyConnectedError
from exitmap.storage.db import Database

linux_only = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "exitmap.db"


def _add_service_with_evidence(db, account_id):
    with db.conn:
        service_id = db.conn.execute(
            "INSERT INTO services (account_id, domain, name) VALUES (?, 'example.com', 'Example')",
            (account_id,),
        ).lastrowid
        db.conn.execute(
            "INSERT INTO evidence (service_id, provider_message_id, subject, sent_at,"
            " relation_type) VALUES (?, 'm1', 'Bienvenido', '2026-01-01T00:00:00', 'registered')",
            (service_id,),
        )


def _count(db, table):
    return db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_created_accounts_are_listed_after_reopening(db_path):
    with Database(db_path) as db:
        db.add_account(Account(Provider.GMAIL, "ana@example.com"))
        db.add_account(Account(Provider.OUTLOOK, "ana@example.com"))

    with Database(db_path) as db:
        accounts = db.list_accounts()

    assert [(a.provider, a.email) for a in accounts] == [
        (Provider.GMAIL, "ana@example.com"),
        (Provider.OUTLOOK, "ana@example.com"),
    ]


def test_duplicate_is_rejected_after_reopening(db_path):
    with Database(db_path) as db:
        db.add_account(Account(Provider.GMAIL, "ana@example.com"))

    with Database(db_path) as db:
        with pytest.raises(AccountAlreadyConnectedError):
            db.add_account(Account(Provider.GMAIL, "ana@example.com"))
        assert len(db.list_accounts()) == 1


def test_delete_account_cascades_to_services_and_evidence(db_path):
    with Database(db_path) as db:
        kept = db.add_account(Account(Provider.GMAIL, "ana@example.com"))
        removed = db.add_account(Account(Provider.OUTLOOK, "ana@example.com"))
        _add_service_with_evidence(db, kept.id)
        _add_service_with_evidence(db, removed.id)

        db.delete_account(removed.id)

    with Database(db_path) as db:
        assert [a.id for a in db.list_accounts()] == [kept.id]
        assert _count(db, "services") == 1
        assert _count(db, "evidence") == 1


@linux_only
def test_db_file_is_owner_only(db_path):
    Database(db_path).close()

    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
