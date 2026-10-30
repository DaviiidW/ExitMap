"""Analysis of the synthetic test mailbox (spec F2-7, F3-1, F4-1..3)."""

from datetime import UTC, datetime

import pytest
from fakes import FakeMailProvider

from exitmap.app.analysis import analyse
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import LinkSource, RelationType, State, UnsubscribeMethod
from exitmap.providers.base import Folders, Period

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"
CATALOG = load_catalog(CATALOG_PATH)

R, S, A = RelationType.REGISTERED, RelationType.SUBSCRIPTION, RelationType.ACCESS

EXPECTED_GMAIL = {
    "spotify.com": {R, S},
    "amazon.es": {S},
    "tienda-ejemplo.es": {R, S},
    "github.com": {A},
    "bbc.co.uk": {S},
}


def _by_domain(detected):
    return {d.service.domain: d for d in detected}


@pytest.fixture
def gmail_services():
    return _by_domain(analyse(FakeMailProvider(GMAIL), account_id=1, catalog=CATALOG))


def test_each_known_service_has_its_relation_types(gmail_services):
    """F2-7: every service of the test mailbox appears with its relation types."""
    assert {d: s.service.relation_types for d, s in gmail_services.items()} == EXPECTED_GMAIL
    outlook = _by_domain(analyse(FakeMailProvider(OUTLOOK), account_id=2, catalog=CATALOG))
    assert {d: s.service.relation_types for d, s in outlook.items()} == {
        "spotify.com": {S},
        "microsoft.com": {A},
    }


def test_spam_and_trash_services_only_when_chosen():
    detected = _by_domain(
        analyse(
            FakeMailProvider(GMAIL),
            folders=Folders(include_spam=True, include_trash=True),
            catalog=CATALOG,
        )
    )
    assert detected["sorteo-ejemplo.com"].service.relation_types == {S}
    assert detected["viajes-ejemplo.com"].service.relation_types == {R}


def test_period_limits_the_services():
    period = Period(start=datetime(2025, 1, 1, tzinfo=UTC))
    detected = analyse(FakeMailProvider(GMAIL), period=period, catalog=CATALOG)
    assert {d.service.domain for d in detected} == {"spotify.com", "github.com", "tienda-ejemplo.es"}


def test_same_service_in_two_accounts_gives_two_entries():
    """F3-1: one entry per (service, account)."""
    detected = analyse(FakeMailProvider(GMAIL), account_id=1, catalog=CATALOG) + analyse(
        FakeMailProvider(OUTLOOK), account_id=2, catalog=CATALOG
    )
    spotify = [d.service for d in detected if d.service.domain == "spotify.com"]
    assert sorted(s.account_id for s in spotify) == [1, 2]
    assert sorted(s.email_count for s in spotify) == [1, 2]


def test_service_details(gmail_services):
    spotify = gmail_services["spotify.com"]
    service = spotify.service
    assert service.name == "Spotify"
    assert service.state is State.PENDING
    assert service.first_email_at == datetime(2021, 3, 10, 9, 15, tzinfo=UTC)
    assert service.last_email_at == datetime(2025, 6, 1, 18, tzinfo=UTC)
    assert service.email_count == 2
    assert [(e.provider_message_id, e.relation_type) for e in spotify.evidence] == [
        ("g1", R),
        ("g2", S),
    ]
    assert spotify.evidence[1].subject == "Novedades de junio"
    assert service.unsubscribe_method is UnsubscribeMethod.ONE_CLICK
    assert service.unsubscribe_target == "https://www.spotify.com/unsubscribe/abc123"


def test_management_links_from_each_source(gmail_services):
    """F4-3: catalog → link in the emails → homepage."""
    links = {d: (s.service.manage_url, s.service.manage_url_source) for d, s in gmail_services.items()}
    assert links["spotify.com"] == (CATALOG.lookup("spotify.com").manage_url, LinkSource.CATALOG)
    assert links["tienda-ejemplo.es"] == (
        "https://tienda-ejemplo.es/mi-cuenta/ajustes",
        LinkSource.EMAIL,
    )
    assert links["bbc.co.uk"] == ("https://bbc.co.uk/", LinkSource.HOMEPAGE)


def test_unsubscribe_methods(gmail_services):
    methods = {d: s.service.unsubscribe_method for d, s in gmail_services.items()}
    assert methods == {
        "spotify.com": UnsubscribeMethod.ONE_CLICK,
        "amazon.es": UnsubscribeMethod.WEB,
        "tienda-ejemplo.es": UnsubscribeMethod.WEB,
        "github.com": None,
        "bbc.co.uk": UnsubscribeMethod.MAILTO,
    }
    assert gmail_services["tienda-ejemplo.es"].service.name == "Tienda Ejemplo"
