"""Unit tests for PKCE, ``state`` and the authorization URL (plan §4 "OAuth")."""

import base64
import hashlib
import re
import urllib.parse
from datetime import UTC, datetime, timedelta

import pytest

from exitmap.errors import ExitMapError
from exitmap.providers.oauth import (
    OAuthConfig,
    Pkce,
    _tokens,
    authorization_url,
    new_pkce,
    new_state,
    s256_challenge,
)

CONFIG = OAuthConfig(
    auth_endpoint="https://auth.example/authorize",
    token_endpoint="https://auth.example/token",
    client_id="client-123",
    scopes=("read", "openid email"),
    extra_auth_params={"access_type": "offline"},
)
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def test_rfc7636_example_challenge():
    # Appendix B of RFC 7636.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert s256_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_new_pkce_verifier_is_valid_and_matches_challenge():
    pkce = new_pkce()
    assert 43 <= len(pkce.verifier) <= 128
    assert re.fullmatch(r"[A-Za-z0-9\-._~]+", pkce.verifier)
    digest = hashlib.sha256(pkce.verifier.encode()).digest()
    assert pkce.challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def test_pkce_and_state_are_random():
    assert new_pkce() != new_pkce()
    assert new_state() != new_state()
    assert len(new_state()) >= 32


def test_authorization_url_has_every_parameter():
    url = authorization_url(CONFIG, "http://127.0.0.1:5000/", "st", Pkce("v", "ch"))

    parts = urllib.parse.urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == CONFIG.auth_endpoint
    assert "+" not in parts.query  # spaces encoded as %20
    params = dict(urllib.parse.parse_qsl(parts.query))
    assert params == {
        "response_type": "code",
        "client_id": "client-123",
        "redirect_uri": "http://127.0.0.1:5000/",
        "scope": "read openid email",
        "state": "st",
        "code_challenge": "ch",
        "code_challenge_method": "S256",
        "access_type": "offline",
    }


def test_tokens_expiry_from_expires_in():
    tokens = _tokens({"access_token": "a", "expires_in": 3600}, NOW, None)
    assert tokens.expires_at == NOW + timedelta(hours=1)


def test_tokens_without_expires_in_or_with_junk():
    assert _tokens({"access_token": "a"}, NOW, None).expires_at is None
    assert _tokens({"access_token": "a", "expires_in": "x"}, NOW, None).expires_at is None


def test_tokens_keep_previous_refresh_token():
    assert _tokens({"access_token": "a"}, NOW, "old").refresh_token == "old"
    assert _tokens({"access_token": "a", "refresh_token": "new"}, NOW, "old").refresh_token == "new"


def test_answer_without_access_token_is_understandable_error():
    with pytest.raises(ExitMapError):
        _tokens({"token_type": "Bearer"}, NOW, None)
