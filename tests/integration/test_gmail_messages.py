"""Gmail headers, body, account, authorization and revocation against a local server
(plan §4 "Gmail"; spec F1-3, F1-4, F9-3)."""

import threading
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest
from gmail_server import ACCESS_TOKEN, FakeGmail, GmailMessage
from local_server import LocalServer, Reply, closed_port_url

from exitmap.errors import OfflineError, PermissionExpiredError
from exitmap.providers.base import MailProvider
from exitmap.providers.gmail import READONLY_SCOPE, GmailProvider, GoogleEndpoints
from exitmap.providers.http import HttpClient
from exitmap.providers.oauth import Tokens

HEADERS = {
    "From": "Shop <news@shop.example>",
    "Subject": "Bienvenido a Shop",
    "Date": "Thu, 15 Jan 2026 10:00:00 +0000",
    "List-Unsubscribe": "<https://shop.example/u>",
    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    "Received": "from somewhere",
}
MESSAGE = GmailMessage("m1", 0, headers=HEADERS, html="<a href='https://shop.example/account'>x</a>")


def endpoints(url: str) -> GoogleEndpoints:
    return GoogleEndpoints(api=url + "/api", auth=url + "/auth", token=url + "/token",
                           revoke=url + "/revoke")


def tokens() -> Tokens:
    return Tokens(ACCESS_TOKEN, "refresh-1", datetime.now(UTC) + timedelta(hours=1))


@pytest.fixture
def gmail():
    fake = FakeGmail([MESSAGE])
    with LocalServer(fake.handler) as server:
        yield fake, server, GmailProvider("cid", "secret", tokens(), endpoints=endpoints(server.url))


def test_provider_follows_the_protocol(gmail):
    assert isinstance(gmail[2], MailProvider)


def test_headers_come_from_metadata_format(gmail):
    _, server, provider = gmail

    headers = provider.get_headers("m1")

    assert headers == {k: v for k, v in HEADERS.items() if k != "Received"}
    request = server.requests[0]
    assert request.param("format") == "metadata"
    assert request.query["metadataHeaders"] == [
        "From", "Subject", "Date", "List-Unsubscribe", "List-Unsubscribe-Post"
    ]


def test_body_comes_from_full_format(gmail):
    _, server, provider = gmail

    assert provider.get_body("m1") == MESSAGE.html
    assert server.requests[0].param("format") == "full"


def test_account_email_from_profile(gmail):
    assert gmail[2].account_email() == "ana@gmail.com"


def test_revoke_sends_the_refresh_token_and_forgets_tokens(gmail):
    fake, _, provider = gmail

    provider.revoke()

    assert fake.revoked == ["refresh-1"]
    assert provider.session.tokens is None


def test_revoke_without_tokens_cannot_withdraw_the_permission(gmail):
    provider = gmail[2]
    provider.session.tokens = None

    with pytest.raises(PermissionExpiredError):
        provider.revoke()


def test_revoke_without_network_is_offline():
    provider = GmailProvider("cid", "secret", tokens(), HttpClient(timeout=2),
                             endpoints(closed_port_url()))
    with pytest.raises(OfflineError):
        provider.revoke()


def test_the_only_scope_requested_is_gmail_readonly():
    opened: list[str] = []

    def token_server(request):
        return Reply(data={"access_token": ACCESS_TOKEN, "refresh_token": "rt", "expires_in": 60})

    def browser(url: str) -> None:
        opened.append(url)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        redirect = f"{params['redirect_uri']}?code=c&state={params['state']}"
        threading.Thread(target=urllib.request.urlopen, args=(redirect,)).start()

    with LocalServer(token_server) as server:
        provider = GmailProvider("cid", "secret", endpoints=endpoints(server.url),
                                 open_browser=browser)
        provider.authorize()

    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(opened[0]).query))
    assert params["scope"] == READONLY_SCOPE
    assert params["scope"] == "https://www.googleapis.com/auth/gmail.readonly"
    assert params["redirect_uri"].startswith("http://127.0.0.1:")
    assert provider.session.tokens.refresh_token == "rt"
