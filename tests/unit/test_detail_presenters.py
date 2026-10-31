"""Fields, evidence and action texts of the service page (spec F4, F5-2..5, F6)."""

from datetime import datetime, timezone

import pytest

from exitmap.app.services import ServiceDetail
from exitmap.app.unsubscribe import Outcome, UnsubscribeResult
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
from exitmap.errors import OfflineError, UnsubscribeFailedError
from exitmap.ui import strings_es as text
from exitmap.ui.presenters import (
    can_unsubscribe,
    date_text,
    detail_fields,
    evidence_row,
    link_text,
    management_confirmation,
    unsubscribe_result_message,
)

ACCOUNT = Account(Provider.GMAIL, "ana@gmail.com", id=1)
NOON = datetime(2025, 6, 15, 12, tzinfo=timezone.utc)


def _service(**changes):
    values = dict(
        account_id=1, domain="tienda.es", name="Tienda",
        relation_types={RelationType.SUBSCRIPTION, RelationType.REGISTERED},
        first_email_at=NOON.replace(year=2021), last_email_at=NOON, email_count=3,
        state=State.PENDING, manage_url="https://tienda.es/cuenta",
        manage_url_source=LinkSource.EMAIL, unsubscribe_method=UnsubscribeMethod.WEB,
        unsubscribe_target="https://tienda.es/baja",
    )
    values.update(changes)
    return Service(**values)


def test_detail_fields_have_everything_f4_1_asks_for():
    """F4-1, F4-4."""
    fields = dict(detail_fields(ServiceDetail(_service(), ACCOUNT, [])))
    assert fields == {
        text.FIELD_NAME: "Tienda",
        text.FIELD_DOMAIN: "tienda.es",
        text.FIELD_ACCOUNT: "ana@gmail.com",
        text.FIELD_RELATIONS: "Cuenta registrada, Suscripción comercial",
        text.FIELD_FIRST_EMAIL: "15/06/2021",
        text.FIELD_LAST_EMAIL: "15/06/2025",
        text.FIELD_EMAIL_COUNT: "3",
        text.FIELD_STATE: "Pendiente",
        text.FIELD_MANAGE_URL: "https://tienda.es/cuenta (origen: correo)",
    }


@pytest.mark.parametrize(
    "source, label",
    [(LinkSource.CATALOG, "catálogo"), (LinkSource.EMAIL, "correo"),
     (LinkSource.HOMEPAGE, "web principal")],
)
def test_link_says_where_it_comes_from(source, label):
    """F4-4."""
    assert link_text(_service(manage_url_source=source)).endswith(f"(origen: {label})")


def test_link_without_url_or_source():
    assert link_text(_service(manage_url=None)) == text.NO_MANAGE_URL
    assert link_text(_service(manage_url_source=None)) == "https://tienda.es/cuenta"


def test_date_text():
    assert date_text(None) == ""
    assert date_text(NOON) == "15/06/2025"


def test_evidence_row():
    """F4-2."""
    evidence = Evidence("m1", "Bienvenido", NOON, RelationType.REGISTERED)
    assert evidence_row(evidence) == ("Bienvenido", "15/06/2025", "Cuenta registrada")


def test_can_unsubscribe_only_with_subscription_and_method():
    assert can_unsubscribe(_service())
    assert not can_unsubscribe(_service(relation_types={RelationType.ACCESS}))
    assert not can_unsubscribe(_service(unsubscribe_method=None, unsubscribe_target=None))


def test_management_confirmation():
    message = management_confirmation(_service(), text.DELETE_ACCOUNT_ACTION)
    assert "Tienda (tienda.es)" in message and "https://tienda.es/cuenta" in message
    assert "eliminar tu cuenta" in message and "estado" in message


def test_unsubscribe_results():
    """F5-2..5."""
    service = _service()
    assert "Baja realizada" in unsubscribe_result_message(
        UnsubscribeResult(Outcome.DONE), service)
    failed = unsubscribe_result_message(
        UnsubscribeResult(Outcome.FAILED_WEB_OPENED, "https://x", OfflineError()), service)
    assert failed.startswith(OfflineError().problem) and text.UNSUBSCRIBE_WEB_FALLBACK in failed
    failed = unsubscribe_result_message(
        UnsubscribeResult(Outcome.FAILED_WEB_OPENED, "https://x", UnsubscribeFailedError()),
        service)
    assert failed.startswith(UnsubscribeFailedError().problem)
    assert unsubscribe_result_message(UnsubscribeResult(Outcome.WEB_OPENED), service) == \
        text.UNSUBSCRIBE_WEB_OPENED
    mail = unsubscribe_result_message(UnsubscribeResult(Outcome.MAIL_PREPARED), service)
    assert "no lo envía" in mail
