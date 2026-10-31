"""Loopback receiver and whole authorization flow with a real local browser request."""

import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest
from local_server import LocalServer, Reply

from exitmap.errors import (
    AuthorizationDeniedError,
    AuthorizationInvalidError,
    AuthorizationTimeoutError,
)
from exitmap.providers.http import HttpClient
from exitmap.providers.oauth import LoopbackReceiver, OAuthConfig, run_authorization
from exitmap.ui.strings_es import AUTH_PAGE_DONE, AUTH_PAGE_FAILED


def browser_get(url: str) -> tuple[int, str]:
    """What the browser does when the provider redirects it."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def wait_in_thread(receiver: LoopbackReceiver, state: str) -> dict:
    result: dict = {}

    def run() -> None:
        try:
            result["code"] = receiver.wait_for_code(state)
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    result["thread"] = thread
    return result


def finish(result: dict) -> dict:
    result["thread"].join(timeout=5)
    return result


def callback(receiver: LoopbackReceiver, **params: str) -> str:
    return f"http://127.0.0.1:{receiver.port}/?{urllib.parse.urlencode(params)}"


def test_code_received():
    receiver = LoopbackReceiver(timeout=5)
    result = wait_in_thread(receiver, "st")

    status, page = browser_get(callback(receiver, code="c1", state="st"))

    assert finish(result)["code"] == "c1"
    assert status == 200
    assert AUTH_PAGE_DONE in page


def test_other_paths_are_ignored_until_the_redirect():
    receiver = LoopbackReceiver(timeout=5)
    result = wait_in_thread(receiver, "st")

    status, _ = browser_get(f"http://127.0.0.1:{receiver.port}/favicon.ico")
    browser_get(callback(receiver, code="c1", state="st"))

    assert status == 404
    assert finish(result)["code"] == "c1"


def test_wrong_state_rejected():
    receiver = LoopbackReceiver(timeout=5)
    result = wait_in_thread(receiver, "st")

    browser_get(callback(receiver, code="c1", state="forged"))

    assert isinstance(finish(result)["error"], AuthorizationInvalidError)


def test_access_denied_is_understandable():
    receiver = LoopbackReceiver(timeout=5)
    result = wait_in_thread(receiver, "st")

    _, page = browser_get(callback(receiver, error="access_denied", state="st"))

    error = finish(result)["error"]
    assert isinstance(error, AuthorizationDeniedError)
    assert "denegado" in error.user_message
    assert AUTH_PAGE_FAILED in page


def test_timeout():
    receiver = LoopbackReceiver(timeout=0.2)

    with pytest.raises(AuthorizationTimeoutError):
        receiver.wait_for_code("st")


def test_run_authorization_opens_browser_and_exchanges_the_code():
    def token_server(request):
        assert request.form["code"] == "c1"
        return Reply(data={"access_token": "at", "refresh_token": "rt", "expires_in": 60})

    with LocalServer(token_server) as server:
        config = OAuthConfig(
            auth_endpoint="https://auth.example/authorize",
            token_endpoint=server.url + "/token",
            client_id="cid",
            scopes=("read",),
        )
        opened: list[str] = []

        def fake_browser(url: str) -> None:
            opened.append(url)
            params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
            redirect = f"{params['redirect_uri']}?code=c1&state={params['state']}"
            threading.Thread(target=browser_get, args=(redirect,)).start()

        tokens = run_authorization(HttpClient(), config, fake_browser, timeout=5)

    assert tokens.access_token == "at"
    assert opened[0].startswith("https://auth.example/authorize?")
    sent = server.requests[0].form
    assert sent["redirect_uri"].startswith("http://127.0.0.1:")
    assert sent["code_verifier"]
