"""Unit tests for the Gmail listing query (plan §4 "Gmail"; spec F2-1, F2-3)."""

from datetime import UTC, datetime

from exitmap.providers.base import Folders, Period
from exitmap.providers.gmail import (
    READONLY_SCOPE,
    gmail_config,
    include_spam_trash,
    search_query,
)

START = datetime(2025, 10, 31, tzinfo=UTC)
END = datetime(2026, 10, 31, tzinfo=UTC)


def test_whole_mailbox_excludes_sent_and_drafts_only():
    assert search_query(Period(), Folders()) == "-in:sent -in:drafts"
    assert not include_spam_trash(Folders())


def test_period_in_unix_seconds():
    query = search_query(Period(START, END), Folders())
    assert query.startswith(f"after:{int(START.timestamp())} before:{int(END.timestamp())} ")


def test_only_start_or_only_end():
    assert "before:" not in search_query(Period(start=START), Folders())
    assert "after:" not in search_query(Period(end=END), Folders())


def test_spam_only_drops_trash():
    folders = Folders(include_spam=True)
    assert include_spam_trash(folders)
    assert search_query(Period(), folders).endswith("-in:trash")
    assert "-in:spam" not in search_query(Period(), folders)


def test_trash_only_drops_spam():
    folders = Folders(include_trash=True)
    assert search_query(Period(), folders).endswith("-in:spam")
    assert "-in:trash" not in search_query(Period(), folders)


def test_both_folders():
    query = search_query(Period(), Folders(include_spam=True, include_trash=True))
    assert "-in:spam" not in query and "-in:trash" not in query


def test_config_asks_for_offline_access():
    config = gmail_config("cid", "secret")
    assert config.scopes == (READONLY_SCOPE,)
    assert config.client_secret == "secret"
    assert config.extra_auth_params["access_type"] == "offline"
    assert config.redirect_host == "127.0.0.1"
