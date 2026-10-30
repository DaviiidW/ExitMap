from datetime import datetime, timezone

import pytest

from exitmap.domain.models import (
    Account,
    Evidence,
    LinkSource,
    Provider,
    RelationType,
    Service,
    State,
    UnsubscribeMethod,
)
from exitmap.errors import AccountAlreadyConnectedError
from exitmap.storage.db import Database


@pytest.fixture
def db():
    with Database(":memory:") as database:
        yield database


def _tables(db):
    rows = db.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def test_schema_has_all_tables(db):
    assert _tables(db) == {"accounts", "services", "evidence", "settings"}


def test_foreign_keys_are_enabled(db):
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_add_account_sets_id_and_created_at(db):
    account = db.add_account(Account(Provider.GMAIL, "ana@example.com"))

    assert account.id is not None
    assert account.created_at is not None


def test_account_fields_round_trip(db):
    analysed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    db.add_account(
        Account(Provider.OUTLOOK, "ana@example.com", "ref-1", last_complete_analysis_at=analysed)
    )

    [account] = db.list_accounts()

    assert account.provider is Provider.OUTLOOK
    assert account.email == "ana@example.com"
    assert account.client_registration_ref == "ref-1"
    assert account.last_complete_analysis_at == analysed


def test_same_email_with_another_provider_is_allowed(db):
    db.add_account(Account(Provider.GMAIL, "ana@example.com"))
    db.add_account(Account(Provider.OUTLOOK, "ana@example.com"))

    assert len(db.list_accounts()) == 2


def test_duplicate_account_raises_understandable_error(db):
    db.add_account(Account(Provider.GMAIL, "ana@example.com"))

    with pytest.raises(AccountAlreadyConnectedError):
        db.add_account(Account(Provider.GMAIL, "ana@example.com"))


@pytest.fixture
def account(db):
    return db.add_account(Account(Provider.GMAIL, "ana@example.com"))


def test_new_service_is_pending_without_alert(db, account):
    service = db.save_service(Service(account.id, "example.com", "Example"))

    stored = db.get_service(service.id)

    assert stored.state is State.PENDING
    assert stored.state_changed_at is None
    assert stored.has_alert is False
    assert stored.relation_types == set()


def test_service_fields_round_trip(db, account):
    first = datetime(2025, 1, 1, tzinfo=timezone.utc)
    last = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = Service(
        account.id,
        "example.com",
        "Example",
        relation_types={RelationType.REGISTERED, RelationType.SUBSCRIPTION},
        first_email_at=first,
        last_email_at=last,
        email_count=7,
        manage_url="https://example.com/account",
        manage_url_source=LinkSource.CATALOG,
        unsubscribe_method=UnsubscribeMethod.ONE_CLICK,
        unsubscribe_target="https://example.com/unsub",
    )
    db.save_service(service)

    assert db.get_service(service.id) == service


def test_save_existing_service_updates_it(db, account):
    service = db.save_service(Service(account.id, "example.com", "Example"))
    service.name = "Example Inc"
    service.email_count = 3
    service.relation_types = {RelationType.ACCESS}

    db.save_service(service)

    assert db.get_service(service.id) == service
    assert len(db.list_services()) == 1


def test_get_missing_service_returns_none(db):
    assert db.get_service(999) is None


def test_list_services_filters_by_account(db, account):
    other = db.add_account(Account(Provider.OUTLOOK, "ana@example.com"))
    a = db.save_service(Service(account.id, "example.com", "Example"))
    b = db.save_service(Service(other.id, "example.com", "Example"))

    assert [s.id for s in db.list_services(account.id)] == [a.id]
    assert [s.id for s in db.list_services()] == [a.id, b.id]


def test_set_state_records_change_time(db, account):
    service = db.save_service(Service(account.id, "example.com", "Example"))
    changed_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    db.set_state(service.id, State.KEEP, changed_at)

    stored = db.get_service(service.id)
    assert stored.state is State.KEEP
    assert stored.state_changed_at == changed_at


def test_set_state_defaults_change_time_to_now(db, account):
    service = db.save_service(Service(account.id, "example.com", "Example"))
    before = datetime.now(timezone.utc)

    db.set_state(service.id, State.DISMISSED)

    assert db.get_service(service.id).state_changed_at >= before


def test_evidence_round_trip_ordered_by_date(db, account):
    service = db.save_service(Service(account.id, "example.com", "Example"))
    later = Evidence(
        "m2", "Nuevo acceso", datetime(2026, 2, 1, tzinfo=timezone.utc), RelationType.ACCESS,
        service_id=service.id,
    )
    earlier = Evidence(
        "m1", "Bienvenido", datetime(2026, 1, 1, tzinfo=timezone.utc), RelationType.REGISTERED,
        service_id=service.id,
    )
    db.add_evidence(later)
    db.add_evidence(earlier)

    assert db.list_evidence(service.id) == [earlier, later]


def test_setting_missing_returns_default(db):
    assert db.get_setting("session_mode") is None
    assert db.get_setting("session_mode", "0") == "0"


def test_setting_is_written_and_overwritten(db):
    db.set_setting("session_mode", "1")
    db.set_setting("session_mode", "0")

    assert db.get_setting("session_mode") == "0"
