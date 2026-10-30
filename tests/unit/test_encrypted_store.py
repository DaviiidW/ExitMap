import json
import os
import stat
import sys

import pytest

from exitmap.errors import WrongPasswordError
from exitmap.storage.credentials import CredentialStore, EncryptedFileStore

TOKEN = "ya29.secret-refresh-token"


@pytest.fixture
def path(tmp_path):
    return tmp_path / "credentials.enc"


def test_follows_the_protocol(path):
    assert isinstance(EncryptedFileStore.create(path, "pw"), CredentialStore)


def test_round_trip_through_reopen(path):
    store = EncryptedFileStore.create(path, "correct horse")
    store.set("gmail:ana", TOKEN)

    reopened = EncryptedFileStore.open(path, "correct horse")

    assert reopened.get("gmail:ana") == TOKEN


def test_delete_persists(path):
    store = EncryptedFileStore.create(path, "pw")
    store.set("gmail:ana", TOKEN)
    store.delete("gmail:ana")
    store.delete("missing")

    assert EncryptedFileStore.open(path, "pw").get("gmail:ana") is None


def test_file_does_not_contain_token_or_password(path):
    EncryptedFileStore.create(path, "my-master-pw").set("gmail:ana", TOKEN)

    raw = path.read_bytes()

    assert TOKEN.encode() not in raw
    assert b"gmail:ana" not in raw
    assert b"my-master-pw" not in raw


def test_each_store_gets_a_random_salt(tmp_path):
    a, b = tmp_path / "a.enc", tmp_path / "b.enc"
    EncryptedFileStore.create(a, "pw")
    EncryptedFileStore.create(b, "pw")

    assert json.loads(a.read_text())["salt"] != json.loads(b.read_text())["salt"]


def test_wrong_password_gives_understandable_error(path):
    EncryptedFileStore.create(path, "right").set("gmail:ana", TOKEN)

    with pytest.raises(WrongPasswordError) as info:
        EncryptedFileStore.open(path, "wrong")

    assert "incorrecta" in info.value.user_message
    assert TOKEN not in info.value.user_message


def test_retry_after_wrong_password(path):
    EncryptedFileStore.create(path, "right").set("gmail:ana", TOKEN)

    with pytest.raises(WrongPasswordError):
        EncryptedFileStore.open(path, "wrong")

    assert EncryptedFileStore.open(path, "right").get("gmail:ana") == TOKEN


@pytest.mark.parametrize("content", ["not json", "{}", '{"salt": "!!", "data": "x"}'])
def test_damaged_file_is_treated_as_wrong_password(path, content):
    path.write_text(content)

    with pytest.raises(WrongPasswordError):
        EncryptedFileStore.open(path, "pw")


def test_reset_deletes_file_and_allows_new_password(path):
    EncryptedFileStore.create(path, "forgotten").set("gmail:ana", TOKEN)

    EncryptedFileStore.reset(path)

    assert not EncryptedFileStore.exists(path)
    store = EncryptedFileStore.create(path, "new")
    assert store.get("gmail:ana") is None
    assert EncryptedFileStore.open(path, "new").get("gmail:ana") is None


def test_reset_without_file_does_nothing(path):
    EncryptedFileStore.reset(path)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")
def test_file_is_owner_only_on_linux(path):
    EncryptedFileStore.create(path, "pw").set("gmail:ana", TOKEN)

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert not path.with_name(path.name + ".tmp").exists()
