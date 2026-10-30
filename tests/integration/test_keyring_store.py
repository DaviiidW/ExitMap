"""``KeyringStore`` through ``keyring``'s global backend selection, with a fake backend."""

import keyring
import pytest
from fakes import FakeKeyring
from keyring.backends import fail

from exitmap.storage.credentials import KeyringStore, keyring_available


@pytest.fixture
def system_keyring():
    previous = keyring.get_keyring()
    yield
    keyring.set_keyring(previous)


def test_credentials_survive_a_new_store(system_keyring):
    keyring.set_keyring(FakeKeyring())

    KeyringStore().set("gmail:ana", "token")

    assert keyring_available()
    assert KeyringStore().get("gmail:ana") == "token"

    KeyringStore().delete("gmail:ana")
    assert KeyringStore().get("gmail:ana") is None


def test_system_without_keyring_detected(system_keyring):
    keyring.set_keyring(fail.Keyring())

    assert not keyring_available()
