"""Code exchange and refresh against a local token server (plan §4 "OAuth")."""

from datetime import UTC, datetime, timedelta

import pytest
from local_server import LocalServer, Reply, closed_port_url

from exitmap.errors import InvalidRegistrationError, OfflineError, PermissionExpiredError
from exitmap.providers.http import HttpClient, HttpError
from exitmap.providers.oauth import OAuthConfig, Pkce, exchange_code, refresh

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
PKCE = Pkce("verifier-abc", "challenge-abc")
REDIRECT = "http://127.0.0.1:5000/"


def config(server_url: str, secret: str | None = None) -> OAuthConfig:
    return OAuthConfig(
        auth_endpoint=server_url + "/authorize",
        token_endpoint=server_url + "/token",
        client_id="client-123",
        scopes=("read",),
        client_secret=secret,
    )


def token_server(request):
    form = request.form
    if form["grant_type"] == "authorization_code" and form["code"] == "good-code":
        return Reply(data={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600,
                           "id_token": "idt"})
    if form["grant_type"] == "refresh_token" and form["refresh_token"] == "rt-1":
        return Reply(data={"access_token": "at-2", "expires_in": 3600})
    return Reply(400, data={"error": "invalid_grant"})


def test_exchange_code_sends_pkce_verifier_and_returns_tokens():
    with LocalServer(token_server) as server:
        tokens = exchange_code(HttpClient(), config(server.url, "s3"), "good-code", REDIRECT,
                               PKCE, NOW)

    assert tokens.access_token == "at-1"
    assert tokens.refresh_token == "rt-1"
    assert tokens.id_token == "idt"
    assert tokens.expires_at == NOW + timedelta(hours=1)
    sent = server.requests[0]
    assert sent.path == "/token"
    assert sent.form == {
        "grant_type": "authorization_code",
        "code": "good-code",
        "redirect_uri": REDIRECT,
        "code_verifier": "verifier-abc",
        "client_id": "client-123",
        "client_secret": "s3",
    }


def test_refresh_returns_new_access_token_and_keeps_refresh_token():
    with LocalServer(token_server) as server:
        tokens = refresh(HttpClient(), config(server.url), "rt-1", NOW)

    assert tokens.access_token == "at-2"
    assert tokens.refresh_token == "rt-1"
    assert "client_secret" not in server.requests[0].form


def test_refresh_rejected_means_permission_expired():
    with LocalServer(token_server) as server:
        with pytest.raises(PermissionExpiredError) as info:
            refresh(HttpClient(), config(server.url), "revoked", NOW)

    assert "caducado" in info.value.user_message


def test_wrong_registration_data_is_explained():
    reply = Reply(401, data={"error": "invalid_client"})
    with LocalServer(lambda request: reply) as server:
        with pytest.raises(InvalidRegistrationError):
            exchange_code(HttpClient(), config(server.url), "good-code", REDIRECT, PKCE, NOW)
        with pytest.raises(InvalidRegistrationError):
            refresh(HttpClient(), config(server.url), "rt-1", NOW)


def test_exchange_with_bad_code_keeps_http_error():
    with LocalServer(token_server) as server:
        with pytest.raises(HttpError) as info:
            exchange_code(HttpClient(), config(server.url), "bad-code", REDIRECT, PKCE, NOW)

    assert info.value.status == 400


def test_refresh_server_failure_is_not_permission_expired():
    with LocalServer(lambda request: Reply(503, data={})) as server:
        with pytest.raises(HttpError):
            refresh(HttpClient(), config(server.url), "rt-1", NOW)


def test_refresh_without_network_is_offline():
    with pytest.raises(OfflineError):
        refresh(HttpClient(timeout=2), config(closed_port_url()), "rt-1", NOW)
