"""Merge of an analysis into the database (plan §3 "Fusión")."""

from datetime import UTC, datetime

import pytest

from exitmap.app.analysis import AnalysisMode, DetectedService, new_only_period, save_analysis
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
from exitmap.providers.base import Period
from exitmap.storage.db import Database

R, S = RelationType.REGISTERED, RelationType.SUBSCRIPTION


def _at(month, day=1):
    return datetime(2025, month, day, tzinfo=UTC)


def _detected(*emails, domain="shop.com", name="Shop", **fields):
    """``emails``: (message_id, month, relation_type) tuples."""
    evidence = [Evidence(mid, f"Subject {mid}", _at(month), rel) for mid, month, rel in emails]
    dates = [e.sent_at for e in evidence]
    service = Service(
        account_id=None,
        domain=domain,
        name=name,
        relation_types={e.relation_type for e in evidence},
        first_email_at=min(dates),
        last_email_at=max(dates),
        email_count=len({e.provider_message_id for e in evidence}),
        **fields,
    )
    return DetectedService(service, evidence)


@pytest.fixture
def db():
    with Database(":memory:") as database:
        yield database


@pytest.fixture
def account_id(db):
    return db.add_account(Account(Provider.GMAIL, "ana@example.com")).id


def _service(db, account_id, domain="shop.com"):
    return db.find_service(account_id, domain)


def test_new_only_period_starts_at_last_complete_analysis():
    assert new_only_period(Account(Provider.GMAIL, "a@b.com")) == Period()
    account = Account(Provider.GMAIL, "a@b.com", last_complete_analysis_at=_at(3))
    assert new_only_period(account) == Period(start=_at(3))


def test_new_service_is_saved_pending_with_evidence(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, R), ("m2", 2, S))], completed_at=_at(4))
    service = _service(db, account_id)
    assert service.state is State.PENDING
    assert service.account_id == account_id
    assert [e.provider_message_id for e in db.list_evidence(service.id)] == ["m1", "m2"]
    assert db.list_accounts()[0].last_complete_analysis_at == _at(4)


def test_completed_at_defaults_to_now(db, account_id):
    before = datetime.now(UTC)
    save_analysis(db, account_id, [])
    assert db.list_accounts()[0].last_complete_analysis_at >= before


def test_all_mode_recalculates_but_keeps_state(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, R), ("m2", 2, S))])
    service = _service(db, account_id)
    db.set_state(service.id, State.KEEP, _at(3))

    save_analysis(db, account_id, [_detected(("m2", 2, S), domain="shop.com", name="Shop 2")])

    service = _service(db, account_id)
    assert (service.state, service.state_changed_at) == (State.KEEP, _at(3))
    assert (service.name, service.relation_types, service.email_count) == ("Shop 2", {S}, 1)
    assert service.first_email_at == _at(2)
    assert [e.provider_message_id for e in db.list_evidence(service.id)] == ["m2"]


def test_new_only_mode_adds_counts_and_evidence(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, R))])
    save_analysis(
        db,
        account_id,
        [
            _detected(
                ("m2", 5, S),
                name="Other",
                unsubscribe_method=UnsubscribeMethod.WEB,
                unsubscribe_target="https://shop.com/u",
            )
        ],
        AnalysisMode.NEW_ONLY,
    )
    service = _service(db, account_id)
    assert service.email_count == 2
    assert service.relation_types == {R, S}
    assert (service.first_email_at, service.last_email_at) == (_at(1), _at(5))
    assert service.name == "Shop"
    assert (service.unsubscribe_method, service.unsubscribe_target) == (
        UnsubscribeMethod.WEB,
        "https://shop.com/u",
    )
    assert [e.provider_message_id for e in db.list_evidence(service.id)] == ["m1", "m2"]


def test_new_only_mode_ignores_emails_already_saved(db, account_id):
    """Overlapping periods do not count the same email twice."""
    save_analysis(db, account_id, [_detected(("m1", 1, R), ("m1", 1, S))])
    save_analysis(db, account_id, [_detected(("m1", 1, R), ("m1", 1, S))], AnalysisMode.NEW_ONLY)
    service = _service(db, account_id)
    assert service.email_count == 1
    assert len(db.list_evidence(service.id)) == 2


def test_new_only_mode_fills_a_missing_management_link(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, R))])
    save_analysis(
        db,
        account_id,
        [
            _detected(
                ("m2", 2, R),
                manage_url="https://shop.com/",
                manage_url_source=LinkSource.HOMEPAGE,
            )
        ],
        AnalysisMode.NEW_ONLY,
    )
    service = _service(db, account_id)
    assert service.manage_url == "https://shop.com/"
    assert service.manage_url_source is LinkSource.HOMEPAGE


@pytest.mark.parametrize("mode", list(AnalysisMode))
def test_alert_after_unsubscribed_with_new_later_email(db, account_id, mode):
    save_analysis(db, account_id, [_detected(("m1", 1, S))])
    db.set_state(_service(db, account_id).id, State.UNSUBSCRIBED, _at(2))
    save_analysis(db, account_id, [_detected(("m1", 1, S), ("m2", 3, S))], mode)
    assert _service(db, account_id).has_alert is True


def test_no_alert_for_emails_before_the_state_change(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, S))])
    db.set_state(_service(db, account_id).id, State.UNSUBSCRIBED, _at(6))
    save_analysis(db, account_id, [_detected(("m1", 1, S), ("m2", 3, S))])
    assert _service(db, account_id).has_alert is False


def test_no_alert_for_other_states(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, S))])
    db.set_state(_service(db, account_id).id, State.KEEP, _at(2))
    save_analysis(db, account_id, [_detected(("m2", 3, S))], AnalysisMode.NEW_ONLY)
    assert _service(db, account_id).has_alert is False


def test_cleared_alert_is_not_raised_again_by_the_same_email(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, S))])
    service_id = _service(db, account_id).id
    db.set_state(service_id, State.UNSUBSCRIBED, _at(2))
    save_analysis(db, account_id, [_detected(("m1", 1, S), ("m2", 3, S))])
    db.clear_alert(service_id)
    save_analysis(db, account_id, [_detected(("m1", 1, S), ("m2", 3, S))])
    assert _service(db, account_id).has_alert is False


def test_unsubscribed_without_change_date_alerts_on_any_new_email(db, account_id):
    save_analysis(db, account_id, [_detected(("m1", 1, S))])
    service = _service(db, account_id)
    service.state = State.UNSUBSCRIBED
    db.save_service(service)
    save_analysis(db, account_id, [_detected(("m2", 2, S))], AnalysisMode.NEW_ONLY)
    assert _service(db, account_id).has_alert is True


def test_failure_rolls_back_the_whole_analysis(db, account_id, monkeypatch):
    save_analysis(db, account_id, [_detected(("m1", 1, R))], completed_at=_at(1))

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(db, "set_last_complete_analysis", fail)
    with pytest.raises(OSError):
        save_analysis(
            db, account_id, [_detected(("m2", 2, S)), _detected(("x1", 2, S), domain="new.com")]
        )

    service = _service(db, account_id)
    assert service.email_count == 1
    assert [e.provider_message_id for e in db.list_evidence(service.id)] == ["m1"]
    assert _service(db, account_id, "new.com") is None
    assert db.list_accounts()[0].last_complete_analysis_at == _at(1)
