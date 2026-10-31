"""``HttpClient`` against a local HTTP server (plan §2, §4 "sin conexión", §8)."""

import pytest
from local_server import LocalServer, Reply, closed_port_url

from exitmap.errors import OfflineError
from exitmap.providers.http import MAX_RETRIES, HttpClient, HttpError


class Sleeps(list):
    def __call__(self, seconds: float) -> None:
        self.append(seconds)


def test_get_200_returns_json_and_sends_params_and_headers():
    with LocalServer(lambda request: Reply(data={"ok": True})) as server:
        data = HttpClient().get_json(
            server.url + "/items", params={"q": "after:2026/01/01"}, headers={"X-Test": "1"}
        )

    assert data == {"ok": True}
    request = server.requests[0]
    assert request.method == "GET"
    assert request.param("q") == "after:2026/01/01"
    assert request.headers["X-Test"] == "1"


def test_post_form_and_json():
    with LocalServer(lambda request: Reply(data={"echo": request.body.decode()})) as server:
        form = HttpClient().post_json(server.url, form={"a": "1 2"})
        body = HttpClient().post_json(server.url, json_body={"b": 2})

    assert form == {"echo": "a=1+2"}
    assert server.requests[0].headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert body == {"echo": '{"b": 2}'}
    assert server.requests[1].headers["Content-Type"] == "application/json"


def test_429_is_retried_after_waiting():
    replies = [Reply(429, headers={"Retry-After": "2"}), Reply(429), Reply(data={"n": 1})]
    sleeps = Sleeps()
    with LocalServer(lambda request: replies.pop(0)) as server:
        data = HttpClient(sleep=sleeps).get_json(server.url)

    assert data == {"n": 1}
    assert len(server.requests) == 3
    assert sleeps == [2, 2]


def test_429_gives_up_after_max_retries():
    sleeps = Sleeps()
    with LocalServer(lambda request: Reply(429, data={})) as server:
        with pytest.raises(HttpError) as info:
            HttpClient(sleep=sleeps).get_json(server.url)

    assert info.value.status == 429
    assert len(server.requests) == MAX_RETRIES + 1
    assert len(sleeps) == MAX_RETRIES


def test_500_raises_http_error_without_retry():
    with LocalServer(lambda request: Reply(500, data={"error": "boom"})) as server:
        with pytest.raises(HttpError) as info:
            HttpClient(sleep=Sleeps()).get_json(server.url)

    assert info.value.status == 500
    assert info.value.data == {"error": "boom"}
    assert len(server.requests) == 1


def test_error_with_non_json_body_keeps_status():
    with LocalServer(lambda request: Reply(503, raw=b"<html>down</html>")) as server:
        with pytest.raises(HttpError) as info:
            HttpClient().get_json(server.url)

    assert info.value.status == 503
    assert info.value.data == {}


def test_no_network_raises_offline():
    with pytest.raises(OfflineError) as info:
        HttpClient(timeout=2).get_json(closed_port_url())

    assert "conexión" in info.value.user_message


def test_post_form_returns_the_status_of_a_page_answer():
    """Answers that are not JSON (a web page) are not decoded."""
    with LocalServer(lambda request: Reply(202, raw=b"<html>ok</html>")) as server:
        status = HttpClient().post_form(server.url + "/u", {"List-Unsubscribe": "One-Click"})

    assert status == 202
    assert server.requests[0].body == b"List-Unsubscribe=One-Click"
    assert server.requests[0].headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_post_form_error_status_raises_http_error():
    with LocalServer(lambda request: Reply(500, raw=b"<html>error</html>")) as server:
        with pytest.raises(HttpError) as info:
            HttpClient().post_form(server.url, {"a": "1"})

    assert info.value.status == 500 and info.value.data == {}
