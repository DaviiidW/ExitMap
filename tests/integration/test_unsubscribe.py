"""Unsubscribing against a local server and with a fake opener (spec F5-2..5)."""

import pytest
from fakes import FakeOpener
from local_server import LocalServer, Reply, closed_port_url

from exitmap.app.unsubscribe import Outcome, UnsubscribeService
from exitmap.domain.models import Account, Provider, RelationType, Service, State, UnsubscribeMethod
from exitmap.errors import ExitMapError, OfflineError, UnsubscribeFailedError
from exitmap.providers.http import HttpClient
from exitmap.storage.db import Database


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "exitmap.db"
    with Database(path) as db:
        db.add_account(Account(Provider.GMAIL, "ana@example.com"))
    return path


def _add(db_path, method, target):
    with Database(db_path) as db:
        account_id = db.list_accounts()[0].id
        service = Service(
            account_id=account_id,
            domain="shop.es",
            name="Shop",
            relation_types={RelationType.SUBSCRIPTION},
            unsubscribe_method=method,
            unsubscribe_target=target,
        )
        return db.save_service(service).id


def _state(db_path, service_id):
    with Database(db_path) as db:
        return db.get_service(service_id).state


def _run(db_path, service_id, opener):
    with Database(db_path) as db:
        return UnsubscribeService(db, HttpClient(timeout=2), opener).unsubscribe(service_id)


@pytest.mark.parametrize("status", [200, 202, 204])
def test_one_click_success_marks_unsubscribed(db_path, status):
    """F5-2: 2xx → *unsubscribed*, nothing opened; kept after reopening."""
    with LocalServer(lambda request: Reply(status, raw=b"<p>ok</p>")) as server:
        service_id = _add(db_path, UnsubscribeMethod.ONE_CLICK, server.url + "/u?id=1")
        opener = FakeOpener()

        result = _run(db_path, service_id, opener)

    assert result.outcome is Outcome.DONE and result.error is None
    assert _state(db_path, service_id) is State.UNSUBSCRIBED
    assert opener.urls == [] and opener.mails == []
    request = server.requests[0]
    assert (request.method, request.path, request.param("id")) == ("POST", "/u", "1")
    assert request.form == {"List-Unsubscribe": "One-Click"}


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_one_click_failure_opens_the_web_and_keeps_the_state(db_path, status):
    """F5-3: reason given, web link opened, state unchanged."""
    with LocalServer(lambda request: Reply(status)) as server:
        target = server.url + "/u"
        service_id = _add(db_path, UnsubscribeMethod.ONE_CLICK, target)
        opener = FakeOpener()

        result = _run(db_path, service_id, opener)

    assert result.outcome is Outcome.FAILED_WEB_OPENED
    assert isinstance(result.error, UnsubscribeFailedError)
    assert opener.urls == [target] and result.opened == target
    assert _state(db_path, service_id) is State.PENDING


def test_one_click_without_network_explains_it(db_path):
    """F5-3 without connection: the reason is the missing connection."""
    target = closed_port_url() + "/u"
    service_id = _add(db_path, UnsubscribeMethod.ONE_CLICK, target)
    opener = FakeOpener()

    result = _run(db_path, service_id, opener)

    assert result.outcome is Outcome.FAILED_WEB_OPENED
    assert isinstance(result.error, OfflineError)
    assert opener.urls == [target]
    assert _state(db_path, service_id) is State.PENDING


def test_web_link_is_opened_and_state_kept(db_path):
    """F5-4."""
    service_id = _add(db_path, UnsubscribeMethod.WEB, "https://shop.es/baja?u=1")
    opener = FakeOpener()

    result = _run(db_path, service_id, opener)

    assert result.outcome is Outcome.WEB_OPENED
    assert opener.urls == ["https://shop.es/baja?u=1"]
    assert _state(db_path, service_id) is State.PENDING


def test_mailto_prepares_the_email_without_sending(db_path):
    """F5-5: mail program opened with the message ready; state unchanged."""
    service_id = _add(db_path, UnsubscribeMethod.MAILTO, "mailto:baja@shop.es")
    opener = FakeOpener()

    with LocalServer(lambda request: Reply()) as server:
        result = _run(db_path, service_id, opener)

    assert result.outcome is Outcome.MAIL_PREPARED
    assert opener.mails == ["mailto:baja@shop.es?subject=unsubscribe"] == [result.opened]
    assert opener.urls == [] and server.requests == []
    assert _state(db_path, service_id) is State.PENDING


def test_service_without_method_is_refused(db_path):
    service_id = _add(db_path, None, None)
    opener = FakeOpener()

    with pytest.raises(ExitMapError):
        _run(db_path, service_id, opener)
    assert opener.urls == [] and opener.mails == []
