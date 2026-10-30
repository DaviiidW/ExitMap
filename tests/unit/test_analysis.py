from datetime import UTC, datetime, timedelta, timezone

import pytest

from exitmap.app.analysis import ServiceAggregator, decode_subject, parse_date
from exitmap.domain.catalog import Catalog, CatalogEntry
from exitmap.domain.models import LinkSource, RelationType, State, UnsubscribeMethod

CATALOG = Catalog({"shop.com": CatalogEntry("Shop Catalog", "https://shop.com/close")})


class Bodies:
    """Minimal provider: only ``get_body`` is used when building services."""

    def __init__(self, bodies):
        self.bodies = bodies
        self.read = []

    def get_body(self, message_id):
        self.read.append(message_id)
        return self.bodies.get(message_id, "")


def _headers(sender, subject, date, **extra):
    headers = {"From": sender, "Subject": subject, "Date": date}
    headers.update({name.replace("_", "-"): value for name, value in extra.items()})
    return headers


@pytest.fixture
def aggregator():
    return ServiceAggregator(account_id=7, catalog=CATALOG)


def test_parse_date():
    assert parse_date("Fri, 05 May 2023 12:00:00 +0200") == datetime(
        2023, 5, 5, 12, tzinfo=timezone(timedelta(hours=2))
    )
    assert parse_date("Fri, 05 May 2023 12:00:00 -0000").tzinfo is not None
    assert parse_date("not a date") is None
    assert parse_date(None) is None


def test_decode_subject_keeps_case_and_accents():
    assert decode_subject("=?utf-8?q?Contrase=C3=B1a?=") == "Contraseña"
    assert decode_subject("  Bienvenido  ") == "Bienvenido"


def test_email_without_rule_creates_no_service(aggregator):
    aggregator.add("m1", _headers("Ana <ana@friends.com>", "Hola", "Mon, 1 Jan 2024 10:00:00 +0000"))
    assert aggregator.services() == []


def test_email_without_domain_or_date_is_ignored(aggregator):
    aggregator.add("m1", {"Subject": "Welcome", "Date": "Mon, 1 Jan 2024 10:00:00 +0000"})
    aggregator.add("m2", {"From": "a@shop.com", "Subject": "Welcome", "Date": "nope"})
    assert aggregator.services() == []


def test_aggregates_types_dates_count_and_evidence(aggregator):
    aggregator.add(
        "m2",
        _headers(
            "News <news@mail.club.org>",
            "Weekly news",
            "Mon, 1 Jul 2024 10:00:00 +0000",
            List_Unsubscribe="<https://club.org/u>",
        ),
    )
    aggregator.add("m1", _headers("Club <hi@club.org>", "Welcome!", "Mon, 1 Jan 2024 10:00:00 +0000"))
    aggregator.add("m3", _headers("x@other.org", "Hola", "Mon, 1 Jan 2024 10:00:00 +0000"))

    [detected] = aggregator.services()
    service = detected.service
    assert (service.account_id, service.domain) == (7, "club.org")
    assert service.relation_types == {RelationType.REGISTERED, RelationType.SUBSCRIPTION}
    assert service.first_email_at == datetime(2024, 1, 1, 10, tzinfo=UTC)
    assert service.last_email_at == datetime(2024, 7, 1, 10, tzinfo=UTC)
    assert service.email_count == 2
    assert service.state is State.PENDING
    assert [(e.provider_message_id, e.subject, e.relation_type) for e in detected.evidence] == [
        ("m1", "Welcome!", RelationType.REGISTERED),
        ("m2", "Weekly news", RelationType.SUBSCRIPTION),
    ]


def test_email_with_two_types_gives_two_evidence_items(aggregator):
    aggregator.add(
        "m1",
        _headers(
            "a@club.org",
            "Welcome",
            "Mon, 1 Jan 2024 10:00:00 +0000",
            List_Unsubscribe="<https://club.org/u>",
        ),
    )
    [detected] = aggregator.services()
    assert {e.relation_type for e in detected.evidence} == {
        RelationType.REGISTERED,
        RelationType.SUBSCRIPTION,
    }
    assert detected.service.email_count == 1


def test_name_is_most_frequent_display_name(aggregator):
    for i, sender in enumerate(["Club News <a@club.org>", "Club <b@club.org>", "Club <c@club.org>"]):
        aggregator.add(f"m{i}", _headers(sender, "Welcome", "Mon, 1 Jan 2024 10:00:00 +0000"))
    assert aggregator.services()[0].service.name == "Club"


@pytest.mark.parametrize(("sender", "name"), [("a@shop.com", "Shop Catalog"), ("a@club.org", "club.org")])
def test_name_without_display_name(aggregator, sender, name):
    aggregator.add("m1", _headers(sender, "Welcome", "Mon, 1 Jan 2024 10:00:00 +0000"))
    assert aggregator.services()[0].service.name == name


def test_unsubscribe_from_most_recent_email(aggregator):
    aggregator.add(
        "new",
        _headers(
            "a@club.org",
            "News",
            "Mon, 1 Jul 2024 10:00:00 +0000",
            List_Unsubscribe="<https://club.org/one-click>",
            List_Unsubscribe_Post="List-Unsubscribe=One-Click",
        ),
    )
    aggregator.add(
        "old",
        _headers(
            "a@club.org", "News", "Mon, 1 Jan 2024 10:00:00 +0000", List_Unsubscribe="<mailto:u@club.org>"
        ),
    )
    service = aggregator.services()[0].service
    assert service.unsubscribe_method is UnsubscribeMethod.ONE_CLICK
    assert service.unsubscribe_target == "https://club.org/one-click"


def test_no_unsubscribe_method_without_usable_header(aggregator):
    aggregator.add(
        "m1",
        _headers("a@club.org", "Welcome", "Mon, 1 Jan 2024 10:00:00 +0000", List_Unsubscribe="garbage"),
    )
    service = aggregator.services()[0].service
    assert (service.unsubscribe_method, service.unsubscribe_target) == (None, None)


def test_link_from_registered_email_body(aggregator):
    aggregator.add("m1", _headers("a@club.org", "Welcome", "Mon, 1 Jan 2024 10:00:00 +0000"))
    provider = Bodies({"m1": '<a href="https://club.org/account">Mi cuenta</a>'})
    service = aggregator.services(provider)[0].service
    assert (service.manage_url, service.manage_url_source) == ("https://club.org/account", LinkSource.EMAIL)


def test_bodies_only_read_for_registered_or_access_outside_catalog(aggregator):
    date = "Mon, 1 Jan 2024 10:00:00 +0000"
    aggregator.add("sub", _headers("a@club.org", "News", date, List_Unsubscribe="<https://club.org/u>"))
    aggregator.add("cat", _headers("a@shop.com", "Welcome", date))
    provider = Bodies({"sub": '<a href="https://club.org/account">Cuenta</a>'})

    services = {d.service.domain: d.service for d in aggregator.services(provider)}
    assert provider.read == []
    assert services["club.org"].manage_url_source is LinkSource.HOMEPAGE
    assert services["club.org"].manage_url == "https://club.org/"
    assert services["shop.com"].manage_url_source is LinkSource.CATALOG
    assert services["shop.com"].manage_url == "https://shop.com/close"
