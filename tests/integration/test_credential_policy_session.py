"""Session mode (spec F10-6, F10-7): nothing on disk, results kept across restarts."""

import keyring
import pytest
from fakes import FakeKeyring

from exitmap.domain.models import Account, Provider, Service, State
from exitmap.storage.credentials import StoreNeed, choose_store, set_session_mode
from exitmap.storage.db import Database

DB_NAME = "exitmap.db"


@pytest.fixture
def system_keyring():
    previous = keyring.get_keyring()
    backend = FakeKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def test_session_mode_writes_nothing_and_keeps_results(tmp_path, system_keyring):
    with Database(tmp_path / DB_NAME) as db:
        set_session_mode(db, True)
        account = db.add_account(Account(provider=Provider.GMAIL, email="ana@example.com"))
        service = db.save_service(Service(account_id=account.id, domain="shop.es", name="Shop"))
        db.set_state(service.id, State.KEEP)
        store = choose_store(db, tmp_path).store
        store.set("gmail:ana@example.com", "ya29.token")

        assert store.get("gmail:ana@example.com") == "ya29.token"

    assert sorted(p.name for p in tmp_path.iterdir()) == [DB_NAME]
    assert system_keyring.passwords == {}
    assert b"ya29.token" not in (tmp_path / DB_NAME).read_bytes()

    # Reopening the app: the account must be reconnected, results and states stay.
    with Database(tmp_path / DB_NAME) as db:
        decision = choose_store(db, tmp_path)
        assert decision.need is StoreNeed.NOTHING
        assert decision.store.get("gmail:ana@example.com") is None
        assert db.list_services()[0].state is State.KEEP


def test_keyring_credentials_survive_restart(tmp_path, system_keyring):
    with Database(tmp_path / DB_NAME) as db:
        choose_store(db, tmp_path).store.set("gmail:ana@example.com", "ya29.token")

    with Database(tmp_path / DB_NAME) as db:
        assert choose_store(db, tmp_path).store.get("gmail:ana@example.com") == "ya29.token"
