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
    store_from_choice,
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


def test_choosing_session_mode_turns_the_setting_on(db, tmp_path):
    """F10-2: choosing session mode keeps it as the setting."""
    store = store_from_choice(db, tmp_path, password=None)

    assert isinstance(store, MemoryStore)
    assert session_mode(db)
    assert list(tmp_path.iterdir()) == []


def test_choosing_a_password_creates_the_encrypted_file(db, tmp_path):
    store = store_from_choice(db, tmp_path, "clave")

    assert isinstance(store, EncryptedFileStore)
    assert not session_mode(db)
    assert EncryptedFileStore.exists(tmp_path / CREDENTIALS_FILE_NAME)


def test_enable_session_mode_deletes_the_given_keys_and_the_file(tmp_path):
    """F10-6."""
    from fakes import FakeKeyring

    from exitmap.storage.credentials import (
        CREDENTIALS_FILE_NAME,
        EncryptedFileStore,
        KeyringStore,
        MemoryStore,
        enable_session_mode,
        session_mode,
    )
    from exitmap.storage.db import Database

    keyring = FakeKeyring()
    store = KeyringStore(keyring)
    store.set("a", "1")
    store.set("b", "2")
    EncryptedFileStore.create(tmp_path / CREDENTIALS_FILE_NAME, "pw")
    with Database(":memory:") as db:
        new = enable_session_mode(db, tmp_path, store, ["a", "b", "missing"])
        assert isinstance(new, MemoryStore) and session_mode(db)
    assert keyring.passwords == {}
    assert not (tmp_path / CREDENTIALS_FILE_NAME).exists()


def test_enable_session_mode_with_locked_keyring_changes_nothing(tmp_path):
    import pytest
    from fakes import FakeKeyring

    from exitmap.errors import KeyringUnavailableError
    from exitmap.storage.credentials import KeyringStore, enable_session_mode, session_mode
    from exitmap.storage.db import Database

    with Database(":memory:") as db:
        with pytest.raises(KeyringUnavailableError):
            enable_session_mode(db, tmp_path, KeyringStore(FakeKeyring(fail=True)), ["a"])
        assert not session_mode(db)
