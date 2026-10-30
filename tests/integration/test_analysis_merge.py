"""Saving and merging analyses of the test mailbox (spec F2-8, F7-1, F8-3, F8-4, F8-6)."""

from datetime import UTC, datetime

import pytest
from fakes import FakeMailProvider

from exitmap.app.analysis import AnalysisMode, analyse, new_only_period, save_analysis
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import Account, Provider, RelationType, State
from exitmap.providers.base import Period
from exitmap.storage.db import Database

GMAIL = "ana.prueba@gmail.com"
CATALOG = load_catalog(CATALOG_PATH)
FIRST_ANALYSIS_AT = datetime(2025, 1, 1, tzinfo=UTC)

R, S, A = RelationType.REGISTERED, RelationType.SUBSCRIPTION, RelationType.ACCESS


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "exitmap.db"


@pytest.fixture
def account_id(db_path):
    """Account whose first complete analysis covered the mailbox until 2025-01-01."""
    with Database(db_path) as db:
        account_id = db.add_account(Account(Provider.GMAIL, GMAIL)).id
        _run(db, account_id, Period(end=FIRST_ANALYSIS_AT), completed_at=FIRST_ANALYSIS_AT)
    return account_id


def _run(db, account_id, period=Period(), mode=AnalysisMode.ALL, completed_at=None):
    detected = analyse(FakeMailProvider(GMAIL), period, account_id=account_id, catalog=CATALOG)
    save_analysis(db, account_id, detected, mode, completed_at)


def _services(db_path):
    with Database(db_path) as db:
        return {s.domain: s for s in db.list_services()}


def _evidence_ids(db_path, service):
    with Database(db_path) as db:
        return [e.provider_message_id for e in db.list_evidence(service.id)]


def test_complete_analysis_is_kept_after_reopening(db_path, account_id):
    """F2-8 and F7-1: services, evidence and last analysis date persist; all pending."""
    services = _services(db_path)
    assert set(services) == {"spotify.com", "amazon.es", "tienda-ejemplo.es", "bbc.co.uk"}
    assert {s.state for s in services.values()} == {State.PENDING}
    assert _evidence_ids(db_path, services["spotify.com"]) == ["g1"]
    with Database(db_path) as db:
        assert db.list_accounts()[0].last_complete_analysis_at == FIRST_ANALYSIS_AT


def test_new_only_adds_new_emails_and_services(db_path, account_id):
    with Database(db_path) as db:
        account = db.list_accounts()[0]
        _run(db, account_id, new_only_period(account), AnalysisMode.NEW_ONLY)

    services = _services(db_path)
    assert set(services) == {
        "spotify.com", "amazon.es", "tienda-ejemplo.es", "bbc.co.uk", "github.com"
    }
    spotify = services["spotify.com"]
    assert (spotify.email_count, spotify.relation_types) == (2, {R, S})
    assert _evidence_ids(db_path, spotify) == ["g1", "g2"]
    assert services["tienda-ejemplo.es"].email_count == 2
    assert services["github.com"].state is State.PENDING
    with Database(db_path) as db:
        assert db.list_accounts()[0].last_complete_analysis_at > FIRST_ANALYSIS_AT


@pytest.mark.parametrize("mode", list(AnalysisMode))
def test_states_are_kept_by_a_reanalysis(db_path, account_id, mode):
    """F8-3."""
    states = {
        "spotify.com": State.KEEP,
        "amazon.es": State.DISMISSED,
        "bbc.co.uk": State.ACCOUNT_DELETED,
    }
    with Database(db_path) as db:
        for domain, state in states.items():
            db.set_state(db.find_service(account_id, domain).id, state)
        _run(db, account_id, mode=mode)

    services = _services(db_path)
    assert {d: services[d].state for d in states} == states
    assert services["tienda-ejemplo.es"].state is State.PENDING


def test_all_mode_recalculates_statistics_and_evidence(db_path, account_id):
    with Database(db_path) as db:
        _run(db, account_id)
    spotify = _services(db_path)["spotify.com"]
    assert spotify.email_count == 2
    assert _evidence_ids(db_path, spotify) == ["g1", "g2"]


def test_services_not_detected_again_are_kept(db_path, account_id):
    """F8-6: a complete re-analysis that no longer finds a service keeps it as it was."""
    before = _services(db_path)
    with Database(db_path) as db:
        db.set_state(before["amazon.es"].id, State.KEEP, FIRST_ANALYSIS_AT)
        _run(db, account_id, Period(start=FIRST_ANALYSIS_AT))

    after = _services(db_path)
    assert after["bbc.co.uk"] == before["bbc.co.uk"]
    assert after["amazon.es"].state is State.KEEP
    assert after["amazon.es"].email_count == before["amazon.es"].email_count
    assert _evidence_ids(db_path, after["amazon.es"]) == ["g3"]


@pytest.mark.parametrize("mode", list(AnalysisMode))
def test_alert_after_unsubscribed_service_sends_again(db_path, account_id, mode):
    """F8-4: an email after the change to *unsubscribed* highlights the service."""
    with Database(db_path) as db:
        spotify_id = db.find_service(account_id, "spotify.com").id
        amazon_id = db.find_service(account_id, "amazon.es").id
        db.set_state(spotify_id, State.UNSUBSCRIBED, datetime(2025, 3, 1, tzinfo=UTC))
        db.set_state(amazon_id, State.UNSUBSCRIBED, datetime(2025, 3, 1, tzinfo=UTC))
        account = db.list_accounts()[0]
        period = new_only_period(account) if mode is AnalysisMode.NEW_ONLY else Period()
        _run(db, account_id, period, mode)

    services = _services(db_path)
    assert services["spotify.com"].has_alert is True
    assert services["spotify.com"].state is State.UNSUBSCRIBED
    assert services["amazon.es"].has_alert is False


def test_cleared_alert_does_not_come_back_with_the_same_emails(db_path, account_id):
    """F8-5 with the answer of the developer: only emails not seen before raise an alert."""
    with Database(db_path) as db:
        spotify_id = db.find_service(account_id, "spotify.com").id
        db.set_state(spotify_id, State.UNSUBSCRIBED, datetime(2025, 3, 1, tzinfo=UTC))
        _run(db, account_id)
        db.clear_alert(spotify_id)

    with Database(db_path) as db:
        _run(db, account_id)

    assert _services(db_path)["spotify.com"].has_alert is False


def test_failed_save_keeps_the_last_complete_analysis(db_path, account_id, monkeypatch):
    before = _services(db_path)
    with Database(db_path) as db:
        monkeypatch.setattr(db, "set_last_complete_analysis", _fail)
        with pytest.raises(OSError):
            _run(db, account_id)

    assert _services(db_path) == before
    with Database(db_path) as db:
        assert db.list_accounts()[0].last_complete_analysis_at == FIRST_ANALYSIS_AT


def _fail(*args):
    raise OSError("disk full")
