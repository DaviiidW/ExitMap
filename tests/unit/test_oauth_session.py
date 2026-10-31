"""Unit tests for ``OAuthSession``: automatic refresh (plan §4 "OAuth")."""

from datetime import UTC, datetime, timedelta

import pytest

from exitmap.errors import PermissionExpiredError
from exitmap.providers.http import HttpError
from exitmap.providers.oauth import OAuthConfig, OAuthSession, Tokens

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
CONFIG = OAuthConfig("https://a/auth", "https://a/token", "cid", ("read",))


class FakeHttp:
    """Answers API calls from ``api`` (list of status/data) and token calls from ``token``."""

    def __init__(self, api, token=None):
        self.api = list(api)
        self.token = list(token or [])
        self.auth_headers: list[str] = []

    def get_json(self, url, params=None, headers=None):
        self.auth_headers.append(headers["Authorization"])
        status, data = self.api.pop(0)
        if status != 200:
            raise HttpError(status, data)
        return data

    def post_json(self, url, form=None, json_body=None, headers=None):
        status, data = self.token.pop(0)
        if status != 200:
            raise HttpError(status, data)
        return data


def tokens(expires_at=NOW + timedelta(hours=1), refresh="rt"):
    return Tokens("at-old", refresh, expires_at)


def session(http, toks):
    return OAuthSession(http, CONFIG, toks, clock=lambda: NOW)


def test_valid_token_is_used_as_is():
    http = FakeHttp([(200, {"ok": 1})])
    assert session(http, tokens()).get_json("https://api") == {"ok": 1}
    assert http.auth_headers == ["Bearer at-old"]


def test_token_about_to_expire_is_refreshed_first():
    http = FakeHttp([(200, {})], token=[(200, {"access_token": "at-new", "expires_in": 3600})])
    s = session(http, tokens(expires_at=NOW + timedelta(seconds=30)))

    s.get_json("https://api")

    assert http.auth_headers == ["Bearer at-new"]
    assert s.tokens.access_token == "at-new"
    assert s.tokens.refresh_token == "rt"


def test_401_refreshes_once_and_retries():
    http = FakeHttp([(401, {}), (200, {"ok": 1})], token=[(200, {"access_token": "at-new"})])

    assert session(http, tokens()).get_json("https://api") == {"ok": 1}
    assert http.auth_headers == ["Bearer at-old", "Bearer at-new"]


def test_401_after_refresh_is_permission_expired():
    http = FakeHttp([(401, {}), (401, {})], token=[(200, {"access_token": "at-new"})])
    with pytest.raises(PermissionExpiredError):
        session(http, tokens()).get_json("https://api")


def test_rejected_refresh_is_permission_expired():
    http = FakeHttp([], token=[(400, {"error": "invalid_grant"})])
    with pytest.raises(PermissionExpiredError):
        session(http, tokens(expires_at=NOW)).get_json("https://api")


def test_other_errors_are_not_retried():
    http = FakeHttp([(500, {})])
    with pytest.raises(HttpError):
        session(http, tokens()).get_json("https://api")
    assert len(http.auth_headers) == 1


@pytest.mark.parametrize("toks", [None, tokens(expires_at=NOW, refresh=None)])
def test_without_tokens_or_refresh_token_is_permission_expired(toks):
    with pytest.raises(PermissionExpiredError):
        session(FakeHttp([]), toks).get_json("https://api")


def test_tokens_without_expiry_are_not_refreshed():
    http = FakeHttp([(200, {})])
    session(http, tokens(expires_at=None)).get_json("https://api")
    assert http.auth_headers == ["Bearer at-old"]
