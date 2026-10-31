"""Unit tests for the HTTP client helpers (plan §2, §8)."""

import pytest

from exitmap.errors import ExitMapError
from exitmap.providers.http import (
    BACKOFF_SECONDS,
    MAX_WAIT_SECONDS,
    HttpError,
    _decode,
    retry_wait,
)


def test_retry_after_in_seconds_is_used():
    assert retry_wait(0, "5") == 5


def test_retry_after_is_capped():
    assert retry_wait(0, "3600") == MAX_WAIT_SECONDS


def test_without_retry_after_the_wait_grows():
    waits = [retry_wait(attempt, None) for attempt in range(5)]
    assert waits[:3] == list(BACKOFF_SECONDS)
    assert waits[3] == waits[4] == BACKOFF_SECONDS[-1]


def test_retry_after_as_date_falls_back_to_default():
    assert retry_wait(1, "Wed, 21 Oct 2026 07:28:00 GMT") == BACKOFF_SECONDS[1]


def test_decode_empty_body_is_empty_dict():
    assert _decode(b"  ") == {}


def test_decode_invalid_json_is_understandable_error():
    with pytest.raises(ExitMapError) as info:
        _decode(b"<html>")
    assert info.value.user_message


def test_http_error_keeps_status_and_generic_message():
    error = HttpError(400, {"error": "invalid_grant"})
    assert error.status == 400
    assert error.data == {"error": "invalid_grant"}
    assert "invalid_grant" not in error.user_message
