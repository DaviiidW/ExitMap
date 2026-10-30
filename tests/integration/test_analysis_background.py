"""Background analysis with the test mailbox (spec F2-4, F2-5, F2-6, F2-9; plan §2, §3)."""

from datetime import UTC, datetime

import pytest
from fakes import ControlledMailProvider, FakeMailProvider

from exitmap.app.analysis import (
    IN_PROGRESS_KEY,
    AnalysisService,
    Cancelled,
    Failed,
    Finished,
    Progress,
)
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import Account, Provider, State
from exitmap.errors import AnalysisInProgressError, OfflineError
from exitmap.providers.base import Folders, Period
from exitmap.storage.db import Database

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"
CATALOG = load_catalog(CATALOG_PATH)
FIRST_ANALYSIS_AT = datetime(2025, 1, 1, tzinfo=UTC)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "exitmap.db"


@pytest.fixture
def accounts(db_path):
    with Database(db_path) as db:
        gmail = db.add_account(Account(Provider.GMAIL, GMAIL)).id
        outlook = db.add_account(Account(Provider.OUTLOOK, OUTLOOK)).id
    return gmail, outlook


@pytest.fixture
def runner(db_path):
    service = AnalysisService(db_path, catalog=CATALOG)
    yield service
    service.cancel()
    service.join(timeout=5)


@pytest.fixture
def previous(db_path, accounts, runner):
    """A complete analysis until 2025 with one state assigned; returns the DB snapshot."""
    _run(runner, FakeMailProvider(GMAIL), accounts[0], Period(end=FIRST_ANALYSIS_AT))
    with Database(db_path) as db:
        spotify = db.find_service(accounts[0], "spotify.com")
        db.set_state(spotify.id, State.KEEP)
    return _snapshot(db_path)


def _run(runner, provider, account_id, period=Period()):
    runner.start(provider, account_id, period)
    runner.join(timeout=5)
    return _drain(runner)


def _drain(runner):
    events = []
    while not runner.events.empty():
        events.append(runner.events.get_nowait())
    return events


def _snapshot(db_path):
    with Database(db_path) as db:
        services = db.list_services()
        evidence = {s.domain: db.list_evidence(s.id) for s in services}
        analysed = [a.last_complete_analysis_at for a in db.list_accounts()]
        return services, evidence, analysed, db.get_setting(IN_PROGRESS_KEY)


def test_progress_reports_done_of_total_and_saves(db_path, accounts, runner):
    """F2-4: one "n of total" event per message, then the analysis is saved."""
    provider = FakeMailProvider(GMAIL)
    total = len(provider.list_message_ids(Period(), Folders()))

    events = _run(runner, provider, accounts[0])

    assert events[:-1] == [Progress(n, total) for n in range(1, total + 1)]
    services, _, analysed, mark = _snapshot(db_path)
    assert events[-1] == Finished(len(services))
    assert services and analysed[0] is not None
    assert mark is None
    assert not runner.running


def test_cancel_keeps_last_complete_analysis(db_path, accounts, runner, previous):
    """F2-5: cancelling discards the new results and keeps the previous ones and states."""
    provider = ControlledMailProvider(GMAIL, pause_at=3)
    runner.start(provider, accounts[0])
    assert provider.paused.wait(timeout=5)

    runner.cancel()
    provider.resume.set()
    runner.join(timeout=5)

    events = _drain(runner)
    assert events[-1] == Cancelled()
    assert all(isinstance(e, Progress) for e in events[:-1])
    assert _snapshot(db_path) == previous


def test_network_error_keeps_last_complete_analysis(db_path, accounts, runner, previous):
    """F2-6: losing the connection halfway leaves the last complete analysis untouched."""
    provider = ControlledMailProvider(GMAIL, fail_at=4, error=OfflineError())

    events = _run(runner, provider, accounts[0])

    assert events[-1] == Failed(provider.error)
    assert isinstance(events[-1].error, OfflineError)
    assert _snapshot(db_path) == previous


def test_second_analysis_is_rejected_in_any_account(db_path, accounts, runner):
    """F2-9: while one analysis runs, another one cannot start, not even in another account."""
    provider = ControlledMailProvider(GMAIL, pause_at=1)
    runner.start(provider, accounts[0])
    assert provider.paused.wait(timeout=5)

    with pytest.raises(AnalysisInProgressError):
        runner.start(FakeMailProvider(OUTLOOK), accounts[1])
    with pytest.raises(AnalysisInProgressError):
        runner.start(FakeMailProvider(GMAIL), accounts[0])

    provider.resume.set()
    runner.join(timeout=5)
    assert isinstance(_drain(runner)[-1], Finished)
    assert isinstance(_run(runner, FakeMailProvider(OUTLOOK), accounts[1])[-1], Finished)


def test_mark_is_present_if_the_app_closes_mid_analysis(db_path, accounts, runner, previous):
    """Plan §3: the mark stays on disk while running, so a closed app leaves it behind."""
    provider = ControlledMailProvider(GMAIL, pause_at=2)
    runner.start(provider, accounts[0])
    assert provider.paused.wait(timeout=5)

    # State on disk at this moment = what the next start of the app would find.
    services, evidence, analysed, mark = _snapshot(db_path)
    assert mark == str(accounts[0])
    assert (services, evidence, analysed) == previous[:3]

    runner.cancel()
    provider.resume.set()
    runner.join(timeout=5)
    assert _snapshot(db_path)[3] is None
