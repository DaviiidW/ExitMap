"""List, search, filters, detail and states with a populated database
(spec F3-1..4, F4-1, F4-2, F7-2, F8-5)."""

import pytest
from fakes import FakeMailProvider

from exitmap.app.analysis import analyse, save_analysis
from exitmap.app.services import ServiceCatalogue, ServiceFilter
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import Account, Provider, RelationType, State
from exitmap.errors import ExitMapError
from exitmap.storage.db import Database

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"
CATALOG = load_catalog(CATALOG_PATH)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "exitmap.db"
    with Database(path) as db:
        for provider, email in ((Provider.GMAIL, GMAIL), (Provider.OUTLOOK, OUTLOOK)):
            account = db.add_account(Account(provider, email))
            detected = analyse(FakeMailProvider(email), account_id=account.id, catalog=CATALOG)
            save_analysis(db, account.id, detected)
    return path


@pytest.fixture
def db(db_path):
    with Database(db_path) as db:
        yield db


def _ids(db):
    return {a.email: a.id for a in db.list_accounts()}


def _by(db, email, domain):
    return db.find_service(_ids(db)[email], domain)


def _names(services):
    return [(s.name, s.account_id) for s in services]


def test_same_service_in_two_accounts_gives_two_entries(db):
    """F3-1."""
    spotify = [s for s in ServiceCatalogue(db).list() if s.domain == "spotify.com"]
    assert sorted(s.account_id for s in spotify) == sorted(_ids(db).values())


def test_order_is_alert_then_pending_then_rest_by_name(db):
    """F3-2."""
    catalogue = ServiceCatalogue(db)
    bbc = _by(db, GMAIL, "bbc.co.uk")
    github = _by(db, GMAIL, "github.com")
    amazon = _by(db, GMAIL, "amazon.es")
    catalogue.set_state(bbc.id, State.UNSUBSCRIBED)
    db.set_alert(bbc.id)
    catalogue.set_state(github.id, State.KEEP)
    catalogue.set_state(amazon.id, State.DISMISSED)

    names = [s.name for s in catalogue.list()]

    assert names == [
        "BBC",
        "Microsoft account team",
        "Spotify",
        "Spotify",
        "Tienda Ejemplo",
        "Amazon.es",
        "GitHub",
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("spot", {"spotify.com"}),
        ("TIENDA", {"tienda-ejemplo.es"}),
        (".co.uk", {"bbc.co.uk"}),
        ("account team", {"microsoft.com"}),
        ("  ", {"amazon.es", "bbc.co.uk", "github.com", "microsoft.com", "spotify.com",
                "tienda-ejemplo.es"}),
    ],
)
def test_search_by_part_of_name_or_domain(db, text, expected):
    """F3-3."""
    found = ServiceCatalogue(db).list(ServiceFilter(text=text))
    assert {s.domain for s in found} == expected


def test_filters_are_combined(db):
    """F3-4: account, relation type and state must all hold."""
    catalogue = ServiceCatalogue(db)
    gmail_id = _ids(db)[GMAIL]
    catalogue.set_state(_by(db, GMAIL, "amazon.es").id, State.KEEP)

    by_account = catalogue.list(ServiceFilter(account_id=gmail_id))
    by_type = catalogue.list(
        ServiceFilter(account_id=gmail_id, relation_type=RelationType.SUBSCRIPTION)
    )
    by_all = catalogue.list(
        ServiceFilter(
            account_id=gmail_id, relation_type=RelationType.SUBSCRIPTION, state=State.PENDING
        )
    )
    with_text = catalogue.list(
        ServiceFilter(text="bbc", account_id=gmail_id, relation_type=RelationType.ACCESS)
    )

    assert {s.domain for s in by_account} == {
        "amazon.es", "bbc.co.uk", "github.com", "spotify.com", "tienda-ejemplo.es"
    }
    assert {s.domain for s in by_type} == {
        "amazon.es", "bbc.co.uk", "spotify.com", "tienda-ejemplo.es"
    }
    assert {s.domain for s in by_all} == {"bbc.co.uk", "spotify.com", "tienda-ejemplo.es"}
    assert with_text == []  # F3-5: nothing matches


def test_detail_has_the_data_and_the_evidence(db):
    """F4-1 and F4-2."""
    spotify = _by(db, GMAIL, "spotify.com")

    detail = ServiceCatalogue(db).detail(spotify.id)

    assert detail.account.email == GMAIL
    service = detail.service
    assert (service.name, service.domain, service.email_count) == ("Spotify", "spotify.com", 2)
    assert service.relation_types == {RelationType.REGISTERED, RelationType.SUBSCRIPTION}
    assert service.first_email_at < service.last_email_at
    assert service.state is State.PENDING
    assert service.manage_url and service.manage_url_source
    assert [(e.subject, e.sent_at.year) for e in detail.evidence] == [
        ("Welcome to Spotify", 2021),
        ("Novedades de junio", 2025),
    ]


def test_opening_the_detail_removes_the_alert(db_path):
    """F8-5: the alert is gone, also after reopening the database."""
    with Database(db_path) as db:
        bbc = _by(db, GMAIL, "bbc.co.uk")
        db.set_alert(bbc.id)

        assert ServiceCatalogue(db).detail(bbc.id).service.has_alert is False

    with Database(db_path) as db:
        assert not db.get_service(bbc.id).has_alert


@pytest.mark.parametrize("state", list(State))
def test_state_is_kept_after_reopening(db_path, state):
    """F7-2."""
    with Database(db_path) as db:
        github = _by(db, GMAIL, "github.com")
        changed = ServiceCatalogue(db).set_state(github.id, state)
        assert changed.state is state and changed.state_changed_at is not None

    with Database(db_path) as db:
        assert db.get_service(github.id).state is state


def test_unknown_service_gives_an_understandable_error(db):
    catalogue = ServiceCatalogue(db)
    with pytest.raises(ExitMapError):
        catalogue.detail(999)
    with pytest.raises(ExitMapError):
        catalogue.set_state(999, State.KEEP)
