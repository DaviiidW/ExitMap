"""Rows and filter options of the main window (spec F3-3, F3-4, F3-5, F8-4)."""

from exitmap.app.services import ServiceFilter
from exitmap.domain.models import Account, Provider, RelationType, Service, State
from exitmap.ui import strings_es as text
from exitmap.ui.presenters import (
    account_filter_options,
    account_label,
    is_filtered,
    relation_filter_options,
    relations_text,
    service_row,
    state_filter_options,
)

GMAIL = Account(Provider.GMAIL, "ana@gmail.com", id=1)
OUTLOOK = Account(Provider.OUTLOOK, "ana@outlook.com", id=2)


def test_account_label_has_email_and_provider():
    assert account_label(GMAIL) == "ana@gmail.com (Gmail)"
    assert account_label(OUTLOOK) == "ana@outlook.com (Outlook)"


def test_filter_options_start_with_no_filter():
    """F3-4: one value at most per filter, the first one does not filter."""
    assert account_filter_options([GMAIL, OUTLOOK]) == [
        (text.ALL_ACCOUNTS, None),
        ("ana@gmail.com (Gmail)", 1),
        ("ana@outlook.com (Outlook)", 2),
    ]
    relations = relation_filter_options()
    assert relations[0] == (text.ALL_RELATIONS, None)
    assert [value for _, value in relations[1:]] == list(RelationType)
    states = state_filter_options()
    assert states[0] == (text.ALL_STATES, None)
    assert [value for _, value in states[1:]] == list(State)
    assert states[3][0] == "Baja realizada"


def test_is_filtered():
    assert not is_filtered(ServiceFilter())
    assert not is_filtered(ServiceFilter(text="  "))
    assert is_filtered(ServiceFilter(text="spo"))
    assert is_filtered(ServiceFilter(account_id=1))
    assert is_filtered(ServiceFilter(relation_type=RelationType.ACCESS))
    assert is_filtered(ServiceFilter(state=State.KEEP))


def test_relations_in_fixed_order():
    types = {RelationType.ACCESS, RelationType.REGISTERED}
    assert relations_text(types) == "Cuenta registrada, Acceso/permiso concedido"
    assert relations_text(set()) == ""


def test_service_row():
    service = Service(1, "spotify.com", "Spotify", {RelationType.SUBSCRIPTION},
                      state=State.KEEP)
    assert service_row(service, {1: GMAIL}) == (
        "Spotify", "spotify.com", "ana@gmail.com", "Suscripción comercial", "Conservar"
    )


def test_service_with_alert_is_marked():
    """F8-4."""
    service = Service(1, "bbc.co.uk", "BBC", state=State.UNSUBSCRIBED, has_alert=True)
    row = service_row(service, {1: GMAIL})
    assert row[0] == text.ALERT_MARK + "BBC"
    assert row[4] == "Baja realizada"
