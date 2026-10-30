import pytest
from fakes import FakeKeyring
from keyring.backends import fail, null

from exitmap.errors import KeyringUnavailableError
from exitmap.storage.credentials import (
    KEYRING_SERVICE,
    CredentialStore,
    KeyringStore,
    MemoryStore,
    keyring_available,
)


@pytest.fixture(params=["memory", "keyring"])
def store(request):
    return MemoryStore() if request.param == "memory" else KeyringStore(FakeKeyring())


def test_stores_follow_the_protocol(store):
    assert isinstance(store, CredentialStore)


def test_missing_key_is_none(store):
    assert store.get("gmail:ana") is None


def test_set_get_and_replace(store):
    store.set("gmail:ana", "token-1")
    store.set("gmail:ana", "token-2")

    assert store.get("gmail:ana") == "token-2"


def test_delete_removes_only_that_key(store):
    store.set("gmail:ana", "a")
    store.set("outlook:ana", "b")

    store.delete("gmail:ana")

    assert store.get("gmail:ana") is None
    assert store.get("outlook:ana") == "b"


def test_delete_missing_key_does_nothing(store):
    store.delete("gmail:ana")


def test_keyring_store_uses_app_service_name():
    backend = FakeKeyring()

    KeyringStore(backend).set("gmail:ana", "token")

    assert backend.passwords == {(KEYRING_SERVICE, "gmail:ana"): "token"}


@pytest.mark.parametrize("operation", ["get", "set", "delete"])
def test_keyring_failure_gives_understandable_error(operation):
    store = KeyringStore(FakeKeyring(fail=True))
    args = ("gmail:ana", "token") if operation == "set" else ("gmail:ana",)

    with pytest.raises(KeyringUnavailableError):
        getattr(store, operation)(*args)


def test_keyring_available_with_real_backend():
    assert keyring_available(FakeKeyring())


@pytest.mark.parametrize("backend", [fail.Keyring(), null.Keyring()], ids=["fail", "null"])
def test_keyring_absent_detected(backend):
    assert not keyring_available(backend)
