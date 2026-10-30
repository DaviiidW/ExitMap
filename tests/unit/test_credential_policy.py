import pytest
from fakes import FakeKeyring
from keyring.backends import fail

from exitmap.storage.credentials import (
    CREDENTIALS_FILE_NAME,
    EncryptedFileStore,
    KeyringStore,
    MemoryStore,
    StoreNeed,
    choose_store,
    session_mode,
    set_session_mode,
)
from exitmap.storage.db import Database


@pytest.fixture
def db():
    with Database(":memory:") as database:
        yield database


def test_session_mode_off_by_default(db):
    assert not session_mode(db)


def test_session_mode_setting_round_trip(db):
    set_session_mode(db, True)
    assert session_mode(db)

    set_session_mode(db, False)
    assert not session_mode(db)


@pytest.mark.parametrize("backend", [FakeKeyring(), fail.Keyring()], ids=["keyring", "none"])
def test_session_mode_uses_memory(db, tmp_path, backend):
    set_session_mode(db, True)

    decision = choose_store(db, tmp_path, backend)

    assert decision.need is StoreNeed.NOTHING
    assert isinstance(decision.store, MemoryStore)


def test_keyring_available_uses_keyring(db, tmp_path):
    decision = choose_store(db, tmp_path, FakeKeyring())

    assert decision.need is StoreNeed.NOTHING
    assert isinstance(decision.store, KeyringStore)


def test_no_keyring_and_no_file_asks_to_choose(db, tmp_path):
    decision = choose_store(db, tmp_path, fail.Keyring())

    assert decision.need is StoreNeed.CHOICE
    assert decision.store is None


def test_no_keyring_with_encrypted_file_asks_password(db, tmp_path):
    EncryptedFileStore.create(tmp_path / CREDENTIALS_FILE_NAME, "pw")

    decision = choose_store(db, tmp_path, fail.Keyring())

    assert decision.need is StoreNeed.PASSWORD
    assert decision.store is None


def test_session_mode_wins_over_encrypted_file(db, tmp_path):
    EncryptedFileStore.create(tmp_path / CREDENTIALS_FILE_NAME, "pw")
    set_session_mode(db, True)

    assert isinstance(choose_store(db, tmp_path, fail.Keyring()).store, MemoryStore)
