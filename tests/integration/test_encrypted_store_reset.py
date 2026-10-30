"""Forgotten master password (spec F10-5): credentials go, results and states stay."""

from datetime import datetime, timezone

from exitmap.domain.models import Account, Provider, Service, State
from exitmap.storage.credentials import CREDENTIALS_FILE_NAME, EncryptedFileStore
from exitmap.storage.db import Database

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_reset_keeps_database(tmp_path):
    db_path = tmp_path / "exitmap.db"
    cred_path = tmp_path / CREDENTIALS_FILE_NAME
    with Database(db_path) as db:
        account = db.add_account(Account(provider=Provider.GMAIL, email="ana@example.com"))
        service = db.save_service(Service(account_id=account.id, domain="shop.es", name="Shop"))
        db.set_state(service.id, State.KEEP, NOW)
    EncryptedFileStore.create(cred_path, "forgotten").set("gmail:ana@example.com", "token")

    EncryptedFileStore.reset(cred_path)
    EncryptedFileStore.create(cred_path, "new")

    assert EncryptedFileStore.open(cred_path, "new").get("gmail:ana@example.com") is None
    with Database(db_path) as db:
        assert [a.email for a in db.list_accounts()] == ["ana@example.com"]
        assert db.list_services()[0].state is State.KEEP
