"""Removing an account with the fake provider (spec F9-1..4)."""

import pytest
from fakes import FakeKeyring, FakeProviderFactory

from exitmap.app.accounts import (
    PERMISSIONS_URLS,
    AccountService,
    Registration,
    load_tokens,
    tokens_key,
)
from exitmap.app.analysis import analyse, save_analysis
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import Provider, State
from exitmap.errors import KeyringUnavailableError, OfflineError, PermissionExpiredError
from exitmap.storage.credentials import KeyringStore, MemoryStore
from exitmap.storage.db import Database

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"
GOOGLE_REG = Registration("123.apps.googleusercontent.com", "GOCSPX-secret")
MICROSOFT_REG = Registration("00000000-0000-0000-0000-000000000000")
CATALOG = load_catalog(CATALOG_PATH)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "exitmap.db"


def _connect(db, store, factory, provider, email, registration):
    factory.next_email = email
    account = AccountService(db, store, factory).connect(provider, registration).account
    detected = analyse(factory.last, account_id=account.id, catalog=CATALOG)
    save_analysis(db, account.id, detected)
    return account


def test_summary_tells_what_will_be_deleted(db_path):
    """F9-1: the confirmation has the account and how many services go with it."""
    factory = FakeProviderFactory()
    with Database(db_path) as db:
        service = AccountService(db, MemoryStore(), factory)
        account = _connect(db, service.store, factory, Provider.GMAIL, GMAIL, GOOGLE_REG)

        summary = service.removal_summary(account.id)

        assert summary.account.email == GMAIL
        assert summary.service_count == len(db.list_services(account.id)) > 0
        assert not factory.last.revoked  # nothing happens until confirmed


def test_gmail_account_is_revoked_and_deleted(db_path):
    """F9-2 and F9-3: permission withdrawn in Google; nothing comes back after reopening."""
    factory = FakeProviderFactory()
    backend = FakeKeyring()
    store = KeyringStore(backend)
    with Database(db_path) as db:
        gmail = _connect(db, store, factory, Provider.GMAIL, GMAIL, GOOGLE_REG)
        outlook = _connect(db, store, factory, Provider.OUTLOOK, OUTLOOK, MICROSOFT_REG)
        service = AccountService(db, store, factory)
        db.set_state(db.list_services(gmail.id)[0].id, State.KEEP)
        saved_tokens = load_tokens(store.get(tokens_key(Provider.GMAIL, GMAIL)))
        factory.next_email = GMAIL

        result = service.remove(gmail.id)

        assert result.revoked and result.manual_revoke_url is None
        provider, registration, tokens, mail = factory.built[-1]
        assert (provider, registration, tokens) == (Provider.GMAIL, GOOGLE_REG, saved_tokens)
        assert mail.revoked

    with Database(db_path) as db:
        assert [a.id for a in db.list_accounts()] == [outlook.id]
        assert {s.account_id for s in db.list_services()} == {outlook.id}
        rows = db.conn.execute(
            "SELECT COUNT(*) FROM evidence JOIN services ON services.id = service_id"
            " WHERE account_id = ?", (gmail.id,)
        ).fetchone()[0]
        assert rows == 0
        assert db.conn.execute("SELECT COUNT(*) FROM services WHERE account_id = ?",
                               (gmail.id,)).fetchone()[0] == 0
    assert store.get(tokens_key(Provider.GMAIL, GMAIL)) is None
    assert store.get(tokens_key(Provider.OUTLOOK, OUTLOOK)) is not None


def test_outlook_account_gives_manual_instructions(db_path):
    """F9-4: Microsoft does not let the app withdraw its permission."""
    factory = FakeProviderFactory()
    store = MemoryStore()
    with Database(db_path) as db:
        account = _connect(db, store, factory, Provider.OUTLOOK, OUTLOOK, MICROSOFT_REG)

        result = AccountService(db, store, factory).remove(account.id)

        assert not result.revoked
        assert result.manual_revoke_url == PERMISSIONS_URLS[Provider.OUTLOOK]
    with Database(db_path) as db:
        assert db.list_accounts() == [] and db.list_services() == []
    assert store.get(tokens_key(Provider.OUTLOOK, OUTLOOK)) is None


@pytest.mark.parametrize("error", [OfflineError(), PermissionExpiredError()])
def test_gmail_without_network_deletes_locally_and_gives_instructions(db_path, error):
    """F9-4: Google cannot be reached (or the permission is gone) → manual instructions."""
    factory = FakeProviderFactory()
    store = MemoryStore()
    with Database(db_path) as db:
        account = _connect(db, store, factory, Provider.GMAIL, GMAIL, GOOGLE_REG)
        factory.revoke_error = error

        result = AccountService(db, store, factory).remove(account.id)

        assert not result.revoked
        assert result.manual_revoke_url == PERMISSIONS_URLS[Provider.GMAIL]
    with Database(db_path) as db:
        assert db.list_accounts() == [] and db.list_services() == []


def test_without_registration_the_account_is_still_removed(db_path):
    """Session mode after reopening: no registration nor tokens left → instructions."""
    factory = FakeProviderFactory()
    with Database(db_path) as db:
        account = _connect(db, MemoryStore(), factory, Provider.GMAIL, GMAIL, GOOGLE_REG)

        result = AccountService(db, MemoryStore(), factory).remove(account.id)

        assert result.manual_revoke_url == PERMISSIONS_URLS[Provider.GMAIL]
        assert db.list_accounts() == []


def test_keyring_failure_keeps_the_account(db_path):
    """A locked keyring raises an understandable error and nothing is deleted."""
    factory = FakeProviderFactory()
    backend = FakeKeyring()
    store = KeyringStore(backend)
    with Database(db_path) as db:
        account = _connect(db, store, factory, Provider.GMAIL, GMAIL, GOOGLE_REG)
        backend.fail = True

        with pytest.raises(KeyringUnavailableError):
            AccountService(db, store, factory).remove(account.id)

        assert [a.id for a in db.list_accounts()] == [account.id]
