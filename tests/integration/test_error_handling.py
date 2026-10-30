import pytest

from exitmap.errors import ExitMapError, OfflineError


def _fetch_with_network_failure():
    try:
        raise OSError("connection reset sending Authorization: Bearer ya29.secret-token")
    except OSError as exc:
        raise OfflineError() from exc


def test_wrapped_low_level_error_reaches_user_without_details():
    with pytest.raises(ExitMapError) as info:
        _fetch_with_network_failure()

    exc = info.value
    assert isinstance(exc, OfflineError)
    assert isinstance(exc.__cause__, OSError)
    assert "ya29" not in str(exc)
    assert "conexión" in str(exc)
