from datetime import UTC, datetime

import pytest

from exitmap.providers.base import Folders, MailProvider, Period, RevokeNotSupported


def at(year, month=1, day=1):
    return datetime(year, month, day, tzinfo=UTC)


def test_whole_mailbox_contains_everything():
    assert Period().contains(at(1990))
    assert Period().contains(at(2100))


def test_start_is_included_and_end_excluded():
    period = Period(start=at(2024), end=at(2025))
    assert period.contains(at(2024))
    assert period.contains(at(2024, 12, 31))
    assert not period.contains(at(2025))
    assert not period.contains(at(2023, 12, 31))


def test_open_ended_periods():
    assert Period(start=at(2024)).contains(at(2030))
    assert not Period(start=at(2024)).contains(at(2023))
    assert Period(end=at(2024)).contains(at(2000))
    assert not Period(end=at(2024)).contains(at(2024))


def test_folders_spam_and_trash_off_by_default():
    assert Folders() == Folders(include_spam=False, include_trash=False)


def test_revoke_not_supported_is_an_exception():
    with pytest.raises(RevokeNotSupported):
        raise RevokeNotSupported()


def test_object_without_methods_is_not_a_provider():
    class Incomplete:
        def authorize(self):
            pass

    assert not isinstance(Incomplete(), MailProvider)
