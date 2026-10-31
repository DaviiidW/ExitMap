"""Outlook headers, body, account, authorization and revocation against a local server
that imitates Graph (plan §4 "Microsoft"; spec F1-3, F1-4, F9-4)."""

import base64
import json
import threading
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest
from graph_server import ACCESS_TOKEN, FakeGraph, GraphMessage
from local_server import LocalServer, Reply

from exitmap.providers.base import Folders, MailProvider, Period, RevokeNotSupported
from exitmap.providers.oauth import Tokens
from exitmap.providers.outlook import MicrosoftEndpoints, OutlookProvider

HEADERS = {
    "From": "Shop <news@shop.example>",
    "Subject": "Confirma tu cuenta",
    "Date": "Thu, 15 Jan 2026 10:00:00 +0000",
    "List-Unsubscribe": "<mailto:baja@shop.example>",
    "Received": "from somewhere",
}
WANTED = {k: v for k, v in HEADERS.items() if k != "Received"}
MESSAGES = [
    GraphMessage("m1", "2026-01-15T10:00:00Z", headers=HEADERS, html="<p>hola</p>"),
    GraphMessage("m2", "2026-01-16T10:00:00Z", html="texto", content_type="text"),
]


def endpoints(url: str) -> MicrosoftEndpoints:
    return MicrosoftEndpoints(api=url + "/me", auth=url + "/auth", token=url + "/token")


def id_token(email: str) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode()
    return f"h.{claims.rstrip('=')}.s"


def tokens() -> Tokens:
    return Tokens(ACCESS_TOKEN, "rt", datetime.now(UTC) + timedelta(hours=1),
                  id_token("ana@outlook.es"))


@pytest.fixture
def graph():
    fake = FakeGraph(MESSAGES)
    with LocalServer(fake.handler) as server:
        fake.base_url = server.url
        yield server, OutlookProvider("cid", tokens(), endpoints=endpoints(server.url))


def test_provider_follows_the_protocol(graph):
    assert isinstance(graph[1], MailProvider)


def test_headers_from_the_listing_need_no_extra_request(graph):
    server, provider = graph
    provider.list_message_ids(Period(), Folders())
    before = len(server.requests)

    assert provider.get_headers("m1") == WANTED
    assert len(server.requests) == before


def test_headers_missing_in_the_listing_are_asked_per_message(graph):
    server, provider = graph

    assert provider.get_headers("m1") == WANTED
    request = server.requests[-1]
    assert request.path == "/me/messages/m1"
    assert request.param("$select") == "internetMessageHeaders"
    assert provider.get_headers("m2") == {}


def test_html_body(graph):
    server, provider = graph

    assert provider.get_body("m1") == "<p>hola</p>"
    assert server.requests[-1].param("$select") == "body"


def test_text_body_is_not_html(graph):
    assert graph[1].get_body("m2") == ""


def test_account_email_from_id_token(graph):
    assert graph[1].account_email() == "ana@outlook.es"


def test_revoke_is_not_supported(graph):
    server, provider = graph
    before = len(server.requests)

    with pytest.raises(RevokeNotSupported):
        provider.revoke()
    assert len(server.requests) == before


def test_scopes_are_read_only_mail_and_sign_in():
    opened: list[str] = []

    def token_server(request):
        return Reply(data={"access_token": ACCESS_TOKEN, "refresh_token": "rt",
                           "expires_in": 60, "id_token": id_token("ana@hotmail.com")})

    def browser(url: str) -> None:
        opened.append(url)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        redirect = f"{params['redirect_uri']}?code=c&state={params['state']}"
        # The browser resolves ``localhost``; the receiver listens on 127.0.0.1.
        redirect = redirect.replace("//localhost:", "//127.0.0.1:")
        threading.Thread(target=urllib.request.urlopen, args=(redirect,)).start()

    with LocalServer(token_server) as server:
        provider = OutlookProvider("cid", endpoints=endpoints(server.url), open_browser=browser)
        provider.authorize()

    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(opened[0]).query))
    assert params["scope"].split() == ["Mail.Read", "offline_access", "openid", "email"]
    assert params["redirect_uri"].startswith("http://localhost:")
    assert "client_secret" not in server.requests[0].form
    assert provider.account_email() == "ana@hotmail.com"
