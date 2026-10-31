"""OAuth 2.0 for native apps: PKCE, authorization URL, code exchange, refresh and the
loopback receiver (plan §4, §7).

The same standard flow (RFC 8252 loopback + RFC 7636 PKCE with S256) serves both
providers; each one only gives its endpoints, scopes, extra parameters and redirect host
in an ``OAuthConfig`` (constitution 1). Tokens and codes are never logged
(constitution 6).
"""

import base64
import hashlib
import html
import secrets
import time
import urllib.parse
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from exitmap.errors import (
    AuthorizationDeniedError,
    AuthorizationInvalidError,
    AuthorizationTimeoutError,
    ExitMapError,
    InvalidRegistrationError,
    PermissionExpiredError,
)
from exitmap.providers.http import HttpClient, HttpError
from exitmap.ui.strings_es import AUTH_PAGE_DONE, AUTH_PAGE_FAILED, AUTH_PAGE_TITLE

# RFC 7636: the verifier has 43-128 characters; 32 random bytes give 43 in base64url.
VERIFIER_BYTES = 32
STATE_BYTES = 32

# Token endpoint errors that mean the app registration data is wrong (spec F1-2).
REGISTRATION_ERRORS = frozenset({"invalid_client", "unauthorized_client"})

# The receiver always listens on the IPv4 loopback address (RFC 8252 §8.3).
LISTEN_HOST = "127.0.0.1"
# Time the user has to finish the authorization in the browser.
AUTH_TIMEOUT_SECONDS = 300
CALLBACK_PATH = "/"


@dataclass(frozen=True)
class OAuthConfig:
    """What a provider needs for the flow; ``client_secret`` only for Google desktop apps."""

    auth_endpoint: str
    token_endpoint: str
    client_id: str
    scopes: tuple[str, ...]
    client_secret: str | None = None
    extra_auth_params: Mapping[str, str] = field(default_factory=dict)
    # Host written in the redirect URI: Google accepts 127.0.0.1; Microsoft compares it with
    # the registered ``http://localhost`` (plan §4).
    redirect_host: str = LISTEN_HOST


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    id_token: str | None = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def s256_challenge(verifier: str) -> str:
    """``BASE64URL(SHA256(verifier))`` without padding (RFC 7636 §4.2)."""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def new_pkce() -> Pkce:
    verifier = _b64url(secrets.token_bytes(VERIFIER_BYTES))
    return Pkce(verifier, s256_challenge(verifier))


def new_state() -> str:
    """Random, unguessable value checked when the browser comes back (plan §4)."""
    return secrets.token_urlsafe(STATE_BYTES)


def authorization_url(config: OAuthConfig, redirect_uri: str, state: str, pkce: Pkce) -> str:
    """URL to open in the system browser so the user can grant access."""
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(config.scopes),
        "state": state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
        **config.extra_auth_params,
    }
    return f"{config.auth_endpoint}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


def _tokens(data: Mapping[str, Any], now: datetime, previous_refresh: str | None) -> Tokens:
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise ExitMapError()
    try:
        expires_at: datetime | None = now + timedelta(seconds=int(data["expires_in"]))
    except (KeyError, TypeError, ValueError):
        expires_at = None
    return Tokens(
        access_token=access,
        # Some providers only send a new refresh token from time to time: keep the old one.
        refresh_token=data.get("refresh_token") or previous_refresh,
        expires_at=expires_at,
        id_token=data.get("id_token"),
    )


def _client_form(config: OAuthConfig) -> dict[str, str]:
    form = {"client_id": config.client_id}
    if config.client_secret:
        form["client_secret"] = config.client_secret
    return form


def exchange_code(
    http: HttpClient,
    config: OAuthConfig,
    code: str,
    redirect_uri: str,
    pkce: Pkce,
    now: datetime | None = None,
) -> Tokens:
    """Swap the authorization code for tokens.

    Wrong registration data → ``InvalidRegistrationError`` (F1-2).
    """
    now = datetime.now(UTC) if now is None else now
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": pkce.verifier,
        **_client_form(config),
    }
    try:
        data = http.post_json(config.token_endpoint, form=form)
    except HttpError as exc:
        if exc.data.get("error") in REGISTRATION_ERRORS:
            raise InvalidRegistrationError() from exc
        raise
    return _tokens(data, now, None)


def refresh(
    http: HttpClient,
    config: OAuthConfig,
    refresh_token: str,
    now: datetime | None = None,
) -> Tokens:
    """Get a new access token.

    If the provider rejects the refresh (permission expired or withdrawn by the user)
    → ``PermissionExpiredError`` so the app can offer to reconnect (spec §5). Without
    network → ``OfflineError`` (from the HTTP client).
    """
    now = datetime.now(UTC) if now is None else now
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token, **_client_form(config)}
    try:
        data = http.post_json(config.token_endpoint, form=form)
    except HttpError as exc:
        if exc.data.get("error") in REGISTRATION_ERRORS:
            raise InvalidRegistrationError() from exc
        if exc.status in (400, 401):
            raise PermissionExpiredError() from exc
        raise
    return _tokens(data, now, refresh_token)


def _page(message: str) -> bytes:
    title = html.escape(AUTH_PAGE_TITLE)
    return (
        f"<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body><p>{html.escape(message)}</p></body></html>"
    ).encode("utf-8")


class LoopbackReceiver:
    """One-shot local server that receives the browser's redirect (plan §4, §7; spec F1-6).

    It listens on a random port of ``127.0.0.1`` and waits, up to ``timeout`` seconds, for
    the single redirect to ``CALLBACK_PATH``. Requests to other paths (for example the
    browser asking for a favicon) are answered with 404 and ignored.
    """

    def __init__(self, redirect_host: str = LISTEN_HOST, timeout: float = AUTH_TIMEOUT_SECONDS):
        self.timeout = timeout
        self._redirect_host = redirect_host
        self._query: dict[str, str] | None = None
        receiver = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path != CALLBACK_PATH or receiver._query is not None:
                    self.send_error(404)
                    return
                receiver._query = dict(urllib.parse.parse_qsl(parsed.query))
                ok = "code" in receiver._query and "error" not in receiver._query
                body = _page(AUTH_PAGE_DONE if ok else AUTH_PAGE_FAILED)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass  # The request line holds the authorization code.

        self._server = HTTPServer((LISTEN_HOST, 0), _Handler)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def redirect_uri(self) -> str:
        return f"http://{self._redirect_host}:{self.port}{CALLBACK_PATH}"

    def wait_for_code(self, expected_state: str) -> str:
        """Authorization code from the redirect, after checking ``state``.

        - ``state`` missing or different → ``AuthorizationInvalidError``.
        - User cancelled or denied (``error=access_denied``) → ``AuthorizationDeniedError``.
        - Wrong registration data → ``InvalidRegistrationError``.
        - No redirect within ``timeout`` → ``AuthorizationTimeoutError``.
        """
        deadline = time.monotonic() + self.timeout
        try:
            while self._query is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AuthorizationTimeoutError()
                self._server.timeout = remaining
                self._server.handle_request()
        finally:
            self._server.server_close()
        return _code_from(self._query, expected_state)

    def close(self) -> None:
        self._server.server_close()


def _code_from(query: Mapping[str, str], expected_state: str) -> str:
    if not secrets.compare_digest(query.get("state", ""), expected_state):
        raise AuthorizationInvalidError()
    error = query.get("error")
    if error in REGISTRATION_ERRORS:
        raise InvalidRegistrationError()
    if error is not None:
        if error == "access_denied":
            raise AuthorizationDeniedError()
        raise ExitMapError()
    code = query.get("code")
    if not code:
        raise AuthorizationInvalidError()
    return code


def run_authorization(
    http: HttpClient,
    config: OAuthConfig,
    open_browser: Callable[[str], object] = webbrowser.open,
    timeout: float = AUTH_TIMEOUT_SECONDS,
) -> Tokens:
    """Whole loopback flow: open the browser, wait for the redirect and get the tokens."""
    pkce = new_pkce()
    state = new_state()
    receiver = LoopbackReceiver(config.redirect_host, timeout)
    try:
        open_browser(authorization_url(config, receiver.redirect_uri, state, pkce))
        code = receiver.wait_for_code(state)
    finally:
        receiver.close()
    return exchange_code(http, config, code, receiver.redirect_uri, pkce)
