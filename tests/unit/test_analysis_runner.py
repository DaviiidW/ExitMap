"""Progress, cancellation and error reporting of an analysis (spec F2-4, F2-5, F2-9)."""

import logging
import threading

import pytest

from exitmap.app.analysis import (
    AnalysisCancelled,
    AnalysisService,
    Failed,
    analyse,
)
from exitmap.domain.catalog import Catalog
from exitmap.errors import AnalysisInProgressError, ExitMapError, OfflineError
from exitmap.providers.base import Folders, Period
from exitmap.storage.db import Database

HEADERS = {
    "m1": {"From": "Shop <news@shop.com>", "Subject": "Ofertas", "Date":
           "Fri, 05 May 2023 12:00:00 +0000", "List-Unsubscribe": "<https://shop.com/u>"},
    "m2": {"From": "Ana <ana@example.org>", "Subject": "Hola", "Date":
           "Sat, 06 May 2023 12:00:00 +0000"},
}


class Provider:
    """Minimal provider; ``on_headers`` runs before returning each message's headers."""

    def __init__(self, on_headers=None):
        self.on_headers = on_headers or (lambda message_id: None)

    def list_message_ids(self, period, folders):
        return list(HEADERS)

    def get_headers(self, message_id):
        self.on_headers(message_id)
        return HEADERS[message_id]

    def get_body(self, message_id):
        return ""


def test_analyse_reports_progress():
    progress = []
    services = analyse(Provider(), catalog=Catalog({}), on_progress=lambda *p: progress.append(p))
    assert progress == [(1, 2), (2, 2)]
    assert [s.service.domain for s in services] == ["shop.com"]


def test_analyse_stops_when_cancelled():
    cancel = threading.Event()
    read = []

    def on_headers(message_id):
        read.append(message_id)
        cancel.set()

    with pytest.raises(AnalysisCancelled):
        analyse(Provider(on_headers), catalog=Catalog({}), cancel=cancel)
    assert read == ["m1"]


def test_analyse_cancelled_before_start_reads_nothing():
    cancel = threading.Event()
    cancel.set()
    read = []
    with pytest.raises(AnalysisCancelled):
        analyse(Provider(read.append), Period(), Folders(), catalog=Catalog({}), cancel=cancel)
    assert read == []


def _failed_with(tmp_path, error):
    def boom(message_id):
        raise error

    runner = AnalysisService(tmp_path / "exitmap.db", catalog=Catalog({}))
    runner.start(Provider(boom), account_id=1)
    runner.join(timeout=5)
    return runner.events.get_nowait()


def test_known_error_is_passed_to_the_user(tmp_path):
    error = OfflineError()
    assert _failed_with(tmp_path, error) == Failed(error)


def test_unexpected_error_becomes_generic_and_is_logged_without_details(tmp_path, caplog):
    secret = "token-abc123 asunto privado"
    with caplog.at_level(logging.WARNING, logger="exitmap"):
        event = _failed_with(tmp_path, RuntimeError(secret))
    assert type(event.error) is ExitMapError
    assert event.error.user_message
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


def test_lock_is_released_and_mark_cleared_after_failure(tmp_path):
    _failed_with(tmp_path, OfflineError())
    with Database(tmp_path / "exitmap.db") as db:
        assert db.get_setting("analysis_in_progress") is None


def test_start_while_running_is_rejected(tmp_path):
    gate = threading.Event()
    runner = AnalysisService(tmp_path / "exitmap.db", catalog=Catalog({}))
    runner.start(Provider(lambda message_id: gate.wait(timeout=5)), account_id=1)
    assert runner.running
    with pytest.raises(AnalysisInProgressError):
        runner.start(Provider(), account_id=1)
    runner.cancel()
    gate.set()
    runner.join(timeout=5)
    assert not runner.running


def test_join_without_start_returns():
    AnalysisService("unused.db").join(timeout=0)


def test_delete_setting(tmp_path):
    with Database(tmp_path / "exitmap.db") as db:
        db.set_setting("k", "v")
        db.delete_setting("k")
        db.delete_setting("missing")
        assert db.get_setting("k") is None
