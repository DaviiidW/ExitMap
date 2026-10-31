"""OAuth 2.0 for native apps: PKCE, authorization URL, code exchange and refresh (plan §4).

The same standard flow (RFC 8252 loopback + RFC 7636 PKCE with S256) serves both
providers; each one only gives its endpoints, scopes and extra parameters in an
``OAuthConfig`` (constitution 1). Tokens are never logged (constitution 6).
"""

import base64
import hashlib
import secrets
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from exitmap.errors import ExitMapError, InvalidRegistrationError, PermissionExpiredError
from exitmap.providers.http import HttpClient, HttpError

# RFC 7636: the verifier has 43-128 characters; 32 random bytes give 43 in base64url.
VERIFIER_BYTES = 32
STATE_BYTES = 32

# Token endpoint errors that mean the app registration data is wrong (spec F1-2).
REGISTRATION_ERRORS = frozenset({"invalid_client", "unauthorized_client"})


@dataclass(frozen=True)
class OAuthConfig:
    """What a provider needs for the flow; ``client_secret`` only for Google desktop apps."""

    auth_endpoint: str
    token_endpoint: str
    client_id: str
    scopes: tuple[str, ...]
    client_secret: str | None = None
    extra_auth_params: Mapping[str, str] = field(default_factory=dict)


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
