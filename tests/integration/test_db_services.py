from datetime import datetime, timezone

import pytest

from exitmap.domain.models import Account, Evidence, Provider, RelationType, Service, State
from exitmap.storage.db import Database


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "exitmap.db"


@pytest.fixture
def service_id(db_path):
    with Database(db_path) as db:
        account = db.add_account(Account(Provider.GMAIL, "ana@example.com"))
        return db.save_service(Service(account.id, "example.com", "Example")).id


@pytest.mark.parametrize("state", list(State))
def test_changed_state_persists_after_reopening(db_path, service_id, state):
    changed_at = datetime(2026, 3, 1, 10, 30, tzinfo=timezone.utc)
    with Database(db_path) as db:
        db.set_state(service_id, state, changed_at)

    with Database(db_path) as db:
        service = db.get_service(service_id)

    assert service.state is state
    assert service.state_changed_at == changed_at


def test_alert_is_set_and_cleared_across_reopening(db_path, service_id):
    with Database(db_path) as db:
        db.set_alert(service_id)

    with Database(db_path) as db:
        assert db.get_service(service_id).has_alert is True
        db.clear_alert(service_id)

    with Database(db_path) as db:
        assert db.get_service(service_id).has_alert is False


def test_service_evidence_and_settings_persist_after_reopening(db_path, service_id):
    sent_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Database(db_path) as db:
        service = db.get_service(service_id)
        service.relation_types = {RelationType.REGISTERED}
        service.email_count = 2
        db.save_service(service)
        db.add_evidence(
            Evidence("m1", "Bienvenido", sent_at, RelationType.REGISTERED, service_id=service_id)
        )
        db.set_setting("session_mode", "1")

    with Database(db_path) as db:
        assert db.get_service(service_id) == service
        [evidence] = db.list_evidence(service_id)
        assert (evidence.subject, evidence.sent_at) == ("Bienvenido", sent_at)
        assert db.get_setting("session_mode") == "1"
