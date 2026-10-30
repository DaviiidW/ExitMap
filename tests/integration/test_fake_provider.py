"""The fake provider over the synthetic mailbox fulfils ``MailProvider`` (plan §2, §6)."""

from datetime import UTC, datetime

import pytest
from fakes import FakeMailProvider

from exitmap.domain.detection import detect
from exitmap.providers.base import Folders, MailProvider, Period, RevokeNotSupported

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"


@pytest.fixture
def gmail():
    return FakeMailProvider(GMAIL)


def test_fake_fulfils_the_protocol(gmail):
    assert isinstance(gmail, MailProvider)
    assert isinstance(FakeMailProvider(OUTLOOK), MailProvider)


def test_authorize_and_account_email(gmail):
    gmail.authorize()
    assert gmail.authorized
    assert gmail.account_email() == GMAIL


def test_default_folders_exclude_spam_and_trash(gmail):
    ids = gmail.list_message_ids(Period(), Folders())
    assert ids == ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8"]


@pytest.mark.parametrize(
    ("folders", "extra"),
    [
        (Folders(include_spam=True), {"g9"}),
        (Folders(include_trash=True), {"g10"}),
        (Folders(include_spam=True, include_trash=True), {"g9", "g10"}),
    ],
)
def test_spam_and_trash_only_when_chosen(gmail, folders, extra):
    inbox = set(gmail.list_message_ids(Period(), Folders()))
    assert set(gmail.list_message_ids(Period(), folders)) == inbox | extra


def test_filters_by_period(gmail):
    period = Period(start=datetime(2025, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, tzinfo=UTC))
    assert gmail.list_message_ids(period, Folders(include_spam=True)) == ["g2", "g6", "g8", "g9"]


def test_period_and_folders_combine(gmail):
    period = Period(end=datetime(2023, 1, 1, tzinfo=UTC))
    assert gmail.list_message_ids(period, Folders()) == ["g1"]
    assert gmail.list_message_ids(period, Folders(include_trash=True)) == ["g1", "g10"]


def test_headers_and_body(gmail):
    headers = gmail.get_headers("g2")
    assert headers["From"] == "Spotify <news@spotify.com>"
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "spotify.com/account" in gmail.get_body("g2")
    assert gmail.get_body("g10") == ""


def test_mailbox_has_the_known_cases(gmail):
    outlook = FakeMailProvider(OUTLOOK)
    all_folders = Folders(include_spam=True, include_trash=True)
    detected = [
        detect(provider.get_headers(message_id))
        for provider in (gmail, outlook)
        for message_id in provider.list_message_ids(Period(), all_folders)
    ]
    assert set() in detected  # personal email
    for types in ({"registered"}, {"subscription"}, {"access"}):
        assert types in detected


def test_revoke_gmail_and_outlook(gmail):
    gmail.revoke()
    assert gmail.revoked
    with pytest.raises(RevokeNotSupported):
        FakeMailProvider(OUTLOOK).revoke()
