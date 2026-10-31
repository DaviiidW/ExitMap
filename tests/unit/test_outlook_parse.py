"""Unit tests for reading Graph answers and the ``id_token`` (synthetic data, plan §6)."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from exitmap.errors import ExitMapError
from exitmap.providers.oauth import OAuthConfig, OAuthSession, Tokens
from exitmap.providers.outlook import email_from_id_token, wanted_headers


def id_token(claims: dict) -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'RS256'})}.{part(claims)}.signature"


def test_headers_keep_only_wanted_with_usual_names():
    items = [
        {"name": "from", "value": "Shop <news@shop.example>"},
        {"name": "X-Mailer", "value": "y"},
        {"name": "list-unsubscribe-post", "value": "List-Unsubscribe=One-Click"},
    ]
    assert wanted_headers(items) == {
        "From": "Shop <news@shop.example>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    assert wanted_headers(None) == {}


def test_email_claim():
    assert email_from_id_token(id_token({"email": "ana@outlook.es"})) == "ana@outlook.es"


def test_preferred_username_when_no_email_claim():
    assert email_from_id_token(id_token({"preferred_username": "ana@hotmail.com"})) == (
        "ana@hotmail.com"
    )


@pytest.mark.parametrize(
    "token", [None, "", "not-a-jwt", "a.@@@.c", id_token({"name": "Ana"}), id_token({"email": 3})]
)
def test_missing_or_bad_id_token_is_understandable_error(token):
    with pytest.raises(ExitMapError):
        email_from_id_token(token)


def test_refresh_without_id_token_keeps_the_previous_one():
    class Http:
        def post_json(self, url, form=None, json_body=None, headers=None):
            return {"access_token": "new"}

        def get_json(self, url, params=None, headers=None):
            return {}

    now = datetime(2026, 10, 31, tzinfo=UTC)
    session = OAuthSession(
        Http(), OAuthConfig("a", "t", "cid", ("s",)), Tokens("old", "rt", now, "idt"),
        clock=lambda: now + timedelta(hours=1),
    )
    session.get_json("https://api")

    assert session.tokens.access_token == "new"
    assert session.tokens.id_token == "idt"
