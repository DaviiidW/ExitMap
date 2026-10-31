"""Search, filters and order of the service list (spec F3-2..4)."""

from exitmap.app.services import ServiceFilter, matches, sort_key
from exitmap.domain.models import RelationType, Service, State


def _service(name, domain="x.es", state=State.PENDING, alert=False, types=(), account=1):
    return Service(
        account_id=account,
        domain=domain,
        name=name,
        relation_types=set(types),
        state=state,
        has_alert=alert,
    )


def test_empty_filter_matches_everything():
    assert matches(_service("Shop"), ServiceFilter())


def test_search_ignores_case_and_surrounding_spaces():
    service = _service("Mi Tienda", "tienda.es")
    assert matches(service, ServiceFilter(text="  mi TIENDA "))
    assert matches(service, ServiceFilter(text="DA.ES"))
    assert not matches(service, ServiceFilter(text="amazon"))


def test_each_filter_is_checked():
    service = _service("Shop", state=State.KEEP, types=[RelationType.ACCESS], account=2)
    assert matches(service, ServiceFilter(account_id=2, relation_type=RelationType.ACCESS,
                                          state=State.KEEP))
    assert not matches(service, ServiceFilter(account_id=1))
    assert not matches(service, ServiceFilter(relation_type=RelationType.SUBSCRIPTION))
    assert not matches(service, ServiceFilter(state=State.PENDING))


def test_order_groups_then_name():
    services = [
        _service("zeta", state=State.KEEP),
        _service("Beta"),
        _service("alfa", state=State.DISMISSED),
        _service("Omega", state=State.UNSUBSCRIBED, alert=True),
        _service("alfa"),
    ]
    ordered = [(s.name, s.state) for s in sorted(services, key=sort_key)]
    assert ordered == [
        ("Omega", State.UNSUBSCRIBED),
        ("alfa", State.PENDING),
        ("Beta", State.PENDING),
        ("alfa", State.DISMISSED),
        ("zeta", State.KEEP),
    ]
