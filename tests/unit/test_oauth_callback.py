"""Unit tests for reading the authorization redirect (plan §4, §7; spec F1-6)."""

import pytest

from exitmap.errors import (
    AuthorizationDeniedError,
    AuthorizationInvalidError,
    ExitMapError,
    InvalidRegistrationError,
)
from exitmap.providers.oauth import LoopbackReceiver, _code_from


def test_code_with_matching_state():
    assert _code_from({"code": "c1", "state": "s"}, "s") == "c1"


@pytest.mark.parametrize("query", [{"code": "c1"}, {"code": "c1", "state": "other"}])
def test_missing_or_wrong_state_is_rejected(query):
    with pytest.raises(AuthorizationInvalidError):
        _code_from(query, "s")


def test_wrong_state_is_checked_before_the_error():
    with pytest.raises(AuthorizationInvalidError):
        _code_from({"error": "access_denied", "state": "other"}, "s")


def test_access_denied():
    with pytest.raises(AuthorizationDeniedError):
        _code_from({"error": "access_denied", "state": "s"}, "s")


def test_registration_error():
    with pytest.raises(InvalidRegistrationError):
        _code_from({"error": "unauthorized_client", "state": "s"}, "s")


def test_other_error_is_generic():
    with pytest.raises(ExitMapError):
        _code_from({"error": "server_error", "state": "s"}, "s")


def test_missing_code_is_rejected():
    with pytest.raises(AuthorizationInvalidError):
        _code_from({"state": "s"}, "s")


def test_redirect_uri_uses_the_provider_host_and_a_random_port():
    google = LoopbackReceiver()
    microsoft = LoopbackReceiver("localhost")
    try:
        assert google.redirect_uri == f"http://127.0.0.1:{google.port}/"
        assert microsoft.redirect_uri == f"http://localhost:{microsoft.port}/"
        assert google.port != microsoft.port
        assert google.port > 0
    finally:
        google.close()
        microsoft.close()
