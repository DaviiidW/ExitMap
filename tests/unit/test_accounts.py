"""Pure helpers of ``app.accounts``: registration, keys, serialisation and factory."""

from datetime import UTC, datetime

import pytest

from exitmap.app.accounts import (
    PERMISSIONS_URLS,
    AccountService,
    Registration,
    TokenHolder,
    build_provider,
    clean_registration,
    dump_registration,
    dump_tokens,
    load_registration,
    load_tokens,
    registration_key,
    tokens_key,
)
from exitmap.domain.models import Provider
from exitmap.errors import ExitMapError, InvalidRegistrationError
from exitmap.providers.base import MailProvider
from exitmap.providers.gmail import GmailProvider
from exitmap.providers.oauth import Tokens
from exitmap.providers.outlook import OutlookProvider
from exitmap.storage.credentials import MemoryStore
from exitmap.storage.db import Database


def test_registration_is_trimmed():
    cleaned = clean_registration(Provider.GMAIL, Registration(" id \n", "\tsecret "))
    assert cleaned == Registration("id", "secret")


def test_outlook_registration_drops_any_secret():
    assert clean_registration(Provider.OUTLOOK, Registration("id", "x")) == Registration("id")


@pytest.mark.parametrize(
    "provider, registration",
    [
        (Provider.GMAIL, Registration("", "secret")),
        (Provider.GMAIL, Registration("id")),
        (Provider.OUTLOOK, Registration(" ")),
    ],
)
def test_incomplete_registration_is_rejected(provider, registration):
    with pytest.raises(InvalidRegistrationError):
        clean_registration(provider, registration)


def test_keys_depend_on_provider_and_address():
    assert registration_key(Provider.GMAIL) != registration_key(Provider.OUTLOOK)
    assert tokens_key(Provider.GMAIL, "a@x.es") != tokens_key(Provider.OUTLOOK, "a@x.es")
    assert tokens_key(Provider.GMAIL, "a@x.es") != tokens_key(Provider.GMAIL, "b@x.es")


@pytest.mark.parametrize("registration", [Registration("id", "secret"), Registration("id")])
def test_registration_round_trip(registration):
    assert load_registration(dump_registration(registration)) == registration


@pytest.mark.parametrize(
    "tokens",
    [
        Tokens("access", "refresh", datetime(2026, 1, 1, 10, tzinfo=UTC), "id.token.x"),
        Tokens("access", None, None),
    ],
)
def test_tokens_round_trip(tokens):
    assert load_tokens(dump_tokens(tokens)) == tokens


def test_factory_builds_each_provider_with_its_tokens():
    tokens = Tokens("access", "refresh", None)

    gmail = build_provider(Provider.GMAIL, Registration("id", "secret"), tokens)
    outlook = build_provider(Provider.OUTLOOK, Registration("id"))

    assert isinstance(gmail, GmailProvider) and gmail.tokens == tokens
    assert isinstance(outlook, OutlookProvider) and outlook.tokens is None
    for provider in (gmail, outlook):
        assert isinstance(provider, MailProvider) and isinstance(provider, TokenHolder)


def test_every_provider_says_where_to_withdraw_the_permission():
    """F9-4: instructions point to the provider's permissions page."""
    assert set(PERMISSIONS_URLS) == set(Provider)
    assert all(url.startswith("https://") for url in PERMISSIONS_URLS.values())


def test_unknown_account_cannot_be_removed():
    with Database(":memory:") as db, pytest.raises(ExitMapError):
        AccountService(db, MemoryStore()).remove(99)
