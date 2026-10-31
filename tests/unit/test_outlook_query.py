"""Unit tests for the Outlook listing parameters (plan §4 "Microsoft"; spec F2-1, F2-3)."""

from datetime import UTC, datetime, timedelta, timezone

from exitmap.providers.base import Folders, Period
from exitmap.providers.outlook import date_filter, excluded_folders, outlook_config


def test_default_excludes_sent_drafts_junk_and_deleted():
    assert excluded_folders(Folders()) == ["sentitems", "drafts", "junkemail", "deleteditems"]


def test_chosen_folders_are_not_excluded():
    assert "junkemail" not in excluded_folders(Folders(include_spam=True))
    assert "deleteditems" not in excluded_folders(Folders(include_trash=True))
    assert excluded_folders(Folders(True, True)) == ["sentitems", "drafts"]


def test_whole_mailbox_has_no_date_filter():
    assert date_filter(Period()) is None


def test_date_filter_in_utc():
    madrid = timezone(timedelta(hours=2))
    period = Period(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 6, 1, 2, 0, tzinfo=madrid))
    assert date_filter(period) == (
        "receivedDateTime ge 2026-01-01T00:00:00Z and receivedDateTime lt 2026-06-01T00:00:00Z"
    )


def test_config_is_a_public_client_on_localhost():
    config = outlook_config("cid")
    assert config.client_secret is None
    assert config.redirect_host == "localhost"
    assert "/common/" in config.auth_endpoint
