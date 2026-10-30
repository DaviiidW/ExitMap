from datetime import datetime

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


def test_state_values_match_spec_table():
    assert [s.value for s in State] == [
        "pending",
        "keep",
        "unsubscribed",
        "access_revoked",
        "account_deleted",
        "dismissed",
    ]


def test_relation_type_values():
    assert {r.value for r in RelationType} == {"registered", "subscription", "access"}


def test_link_source_values():
    assert {s.value for s in LinkSource} == {"catalog", "email", "homepage"}


def test_unsubscribe_method_values():
    assert {m.value for m in UnsubscribeMethod} == {"one_click", "web", "mailto"}


def test_provider_values():
    assert {p.value for p in Provider} == {"gmail", "outlook"}


def test_enums_round_trip_from_stored_strings():
    assert State("unsubscribed") is State.UNSUBSCRIBED
    assert Provider("gmail") == "gmail"


def test_account_defaults():
    account = Account(provider=Provider.GMAIL, email="ana@example.com")

    assert account.id is None
    assert account.client_registration_ref is None
    assert account.last_complete_analysis_at is None
    assert account.created_at is None


def test_new_service_is_pending():
    service = Service(account_id=1, domain="amazon.es", name="Amazon")

    assert service.state is State.PENDING
    assert service.state_changed_at is None
    assert service.has_alert is False
    assert service.email_count == 0
    assert service.relation_types == set()
    assert service.first_email_at is None and service.last_email_at is None
    assert service.manage_url is None and service.manage_url_source is None
    assert service.unsubscribe_method is None and service.unsubscribe_target is None
    assert service.id is None


def test_services_do_not_share_relation_types():
    first = Service(account_id=1, domain="a.com", name="A")
    second = Service(account_id=1, domain="b.com", name="B")

    first.relation_types.add(RelationType.SUBSCRIPTION)

    assert second.relation_types == set()


def test_evidence_defaults():
    evidence = Evidence(
        provider_message_id="m1",
        subject="Bienvenido",
        sent_at=datetime(2024, 1, 1),
        relation_type=RelationType.REGISTERED,
    )

    assert evidence.service_id is None
    assert evidence.id is None
