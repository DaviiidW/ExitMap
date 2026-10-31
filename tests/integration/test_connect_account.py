"""Connecting accounts with the fake provider (spec F1-2, F1-3, F1-5..7, F10-1, F10-2)."""

import pytest
from fakes import FakeKeyring, FakeProviderFactory
from keyring.backends import fail

from exitmap.app.accounts import (
    AccountService,
    Registration,
    load_tokens,
    registration_key,
    tokens_key,
)
from exitmap.domain.models import Provider
from exitmap.errors import (
    AuthorizationDeniedError,
    InvalidRegistrationError,
    RegistrationMissingError,
)
from exitmap.storage.credentials import (
    CREDENTIALS_FILE_NAME,
    MemoryStore,
    StoreNeed,
    choose_store,
    session_mode,
    store_from_choice,
)
from exitmap.storage.db import Database

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"
GOOGLE_REG = Registration("123.apps.googleusercontent.com", "GOCSPX-secret")
MICROSOFT_REG = Registration("00000000-0000-0000-0000-000000000000")


@pytest.fixture
def db(tmp_path):
    with Database(tmp_path / "exitmap.db") as db:
        yield db


@pytest.fixture
def factory():
    return FakeProviderFactory(GMAIL)


def test_without_registration_it_is_asked_for(db, factory):
    """F1-2: no registration for the provider → it must be entered first."""
    service = AccountService(db, MemoryStore(), factory)

    assert service.needs_registration(Provider.GMAIL)
    with pytest.raises(RegistrationMissingError):
        service.connect(Provider.GMAIL)
    assert factory.built == [] and db.list_accounts() == []


@pytest.mark.parametrize(
    "provider, registration",
    [
        (Provider.GMAIL, Registration("  ", "secret")),
        (Provider.GMAIL, Registration("123.apps.googleusercontent.com", "")),
        (Provider.OUTLOOK, Registration("")),
    ],
)
def test_incomplete_registration_is_explained(db, factory, provider, registration):
    """F1-2: incomplete data → understandable error, nothing saved."""
    store = MemoryStore()
    service = AccountService(db, store, factory)

    with pytest.raises(InvalidRegistrationError) as info:
        service.connect(provider, registration)

    assert info.value.user_message
    assert store.get(registration_key(provider)) is None
    assert db.list_accounts() == []


def test_registration_rejected_by_the_provider_is_not_saved(db, factory):
    """F1-2: the provider rejects the registration data during the authorization."""
    factory.authorize_error = InvalidRegistrationError()
    store = MemoryStore()

    with pytest.raises(InvalidRegistrationError):
        AccountService(db, store, factory).connect(Provider.GMAIL, GOOGLE_REG)

    assert store.get(registration_key(Provider.GMAIL)) is None
    assert db.list_accounts() == []


def test_connected_account_is_listed_with_its_address(db, factory):
    """F1-3: after authorizing, the account appears with its email; registration saved."""
    store = MemoryStore()
    service = AccountService(db, store, factory)

    result = service.connect(Provider.GMAIL, GOOGLE_REG)

    assert factory.last.authorized
    assert not result.already_connected
    assert [(a.provider, a.email) for a in service.list_accounts()] == [(Provider.GMAIL, GMAIL)]
    assert result.account.client_registration_ref == registration_key(Provider.GMAIL)
    assert not service.needs_registration(Provider.GMAIL)
    assert service.registration(Provider.GMAIL) == GOOGLE_REG


def test_saved_registration_is_reused(db, factory):
    service = AccountService(db, MemoryStore(), factory)
    service.connect(Provider.GMAIL, GOOGLE_REG)
    factory.next_email = OUTLOOK  # any address: only the registration matters here

    service.connect(Provider.GMAIL)

    assert factory.built[-1][1] == GOOGLE_REG


def test_second_account_is_listed_too(db, factory):
    """F1-5."""
    service = AccountService(db, MemoryStore(), factory)
    service.connect(Provider.GMAIL, GOOGLE_REG)
    factory.next_email = OUTLOOK

    service.connect(Provider.OUTLOOK, MICROSOFT_REG)

    assert [(a.provider, a.email) for a in service.list_accounts()] == [
        (Provider.GMAIL, GMAIL),
        (Provider.OUTLOOK, OUTLOOK),
    ]


def test_denied_authorization_adds_nothing(db, factory):
    """F1-6: the error explains what happened and no account is added."""
    factory.authorize_error = AuthorizationDeniedError()
    store = MemoryStore()

    with pytest.raises(AuthorizationDeniedError) as info:
        AccountService(db, store, factory).connect(Provider.GMAIL, GOOGLE_REG)

    assert info.value.user_message
    assert db.list_accounts() == []
    assert store.get(tokens_key(Provider.GMAIL, GMAIL)) is None


def test_connecting_again_does_not_duplicate(db, factory):
    """F1-7: not added twice; the result tells it was already connected."""
    service = AccountService(db, MemoryStore(), factory)
    first = service.connect(Provider.GMAIL, GOOGLE_REG)

    again = service.connect(Provider.GMAIL)

    assert again.already_connected
    assert again.account.id == first.account.id
    assert len(service.list_accounts()) == 1


def test_connecting_again_keeps_the_new_tokens(db, factory):
    """Reconnecting (F10-6, F10-7, spec §5) replaces the saved tokens."""
    store = MemoryStore()
    service = AccountService(db, store, factory)
    service.connect(Provider.GMAIL, GOOGLE_REG)
    store.delete(tokens_key(Provider.GMAIL, GMAIL))

    service.connect(Provider.GMAIL)

    assert store.get(tokens_key(Provider.GMAIL, GMAIL)) is not None


def test_keyring_keeps_the_account_connected_after_reopening(tmp_path, factory):
    """F10-1: keyring available, session mode off → credentials in the keyring."""
    backend = FakeKeyring()
    with Database(tmp_path / "exitmap.db") as db:
        decision = choose_store(db, tmp_path, backend)
        AccountService(db, decision.store, factory).connect(Provider.GMAIL, GOOGLE_REG)

    with Database(tmp_path / "exitmap.db") as db:
        store = choose_store(db, tmp_path, backend).store
        service = AccountService(db, store, factory)
        assert [a.email for a in service.list_accounts()] == [GMAIL]
        tokens = load_tokens(store.get(tokens_key(Provider.GMAIL, GMAIL)))
        assert tokens.refresh_token == f"refresh-{GMAIL}"
        assert service.registration(Provider.GMAIL) == GOOGLE_REG
    assert not (tmp_path / CREDENTIALS_FILE_NAME).exists()


def test_without_keyring_choosing_session_mode_is_remembered(tmp_path, factory):
    """F10-2: first account without keyring → choose; session mode stays as the setting."""
    with Database(tmp_path / "exitmap.db") as db:
        no_keyring = fail.Keyring()
        decision = choose_store(db, tmp_path, no_keyring)
        assert decision.need is StoreNeed.CHOICE
        service = AccountService(db, decision.store, factory)
        assert service.store is None

        service.store = store_from_choice(db, tmp_path, password=None)
        service.connect(Provider.GMAIL, GOOGLE_REG)

        assert session_mode(db)
        assert choose_store(db, tmp_path, no_keyring).need is StoreNeed.NOTHING
    assert sorted(p.name for p in tmp_path.iterdir()) == ["exitmap.db"]


def test_without_keyring_choosing_a_password_encrypts_the_credentials(tmp_path, factory):
    """F10-2: master password → encrypted file, asked for when reopening (F10-3)."""
    with Database(tmp_path / "exitmap.db") as db:
        service = AccountService(db, store_from_choice(db, tmp_path, "clave"), factory)
        service.connect(Provider.GMAIL, GOOGLE_REG)

        assert not session_mode(db)
        assert choose_store(db, tmp_path, fail.Keyring()).need is StoreNeed.PASSWORD
    content = (tmp_path / CREDENTIALS_FILE_NAME).read_bytes()
    assert b"refresh-" not in content and b"GOCSPX" not in content


def test_connecting_before_choosing_a_store_is_refused(db, factory):
    with pytest.raises(RuntimeError):
        AccountService(db, None, factory).connect(Provider.GMAIL, GOOGLE_REG)
    assert factory.built == []
