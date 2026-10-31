"""Minimal JSON HTTP client with ``urllib`` (plan §2, §4 "Detección de sin conexión", §8).

- A network failure in any request raises ``OfflineError``: there is no separate check.
- HTTP 429 (quota exceeded) is retried after waiting, using ``Retry-After`` when the
  server sends it and an increasing wait otherwise.
- Any other non-2xx answer raises ``HttpError`` with the status and the decoded body, so
  each provider can map it to its own error (for example, an expired permission).

Nothing here logs URLs, headers or bodies: they may hold tokens or email data
(constitution 6).
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from exitmap.errors import ExitMapError, OfflineError

TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
# Waits (seconds) before each retry when the server does not send ``Retry-After``.
BACKOFF_SECONDS = (1, 2, 4)
MAX_WAIT_SECONDS = 60

TOO_MANY_REQUESTS = 429


class HttpError(ExitMapError):
    """The server answered with a non-2xx status.

    ``data`` is the JSON body when there is one (an empty dict otherwise). The message for
    the user is the generic one; callers raise a more specific error when they can.
    """

    def __init__(self, status: int, data: Mapping[str, Any] | None = None) -> None:
        super().__init__(status)
        self.status = status
        self.data: Mapping[str, Any] = data or {}


def retry_wait(attempt: int, retry_after: str | None) -> float:
    """Seconds to wait before retry number ``attempt`` (0-based) after a 429."""
    if retry_after is not None:
        try:
            return min(max(float(retry_after), 0.0), MAX_WAIT_SECONDS)
        except ValueError:
            pass  # An HTTP date or junk: fall back to the default waits.
    return BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]


def _decode(raw: bytes) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ExitMapError() from exc
    return data if isinstance(data, dict) else {"value": data}


class HttpClient:
    """Sends JSON requests; ``sleep`` and ``timeout`` can be replaced in tests."""

    def __init__(
        self,
        timeout: float = TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = timeout
        self._sleep = sleep

    def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """``GET url?params`` and decode the JSON answer."""
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return self._send("GET", url, None, dict(headers or {}))

    def post_json(
        self,
        url: str,
        form: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """``POST`` a form (``form``) or a JSON document (``json_body``) and decode the answer."""
        all_headers = dict(headers or {})
        body = b""
        if form is not None:
            body = urllib.parse.urlencode(form).encode("ascii")
            all_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            all_headers.setdefault("Content-Type", "application/json")
        return self._send("POST", url, body, all_headers)

    def _send(
        self, method: str, url: str, body: bytes | None, headers: dict[str, str]
    ) -> dict[str, Any]:
        headers.setdefault("Accept", "application/json")
        for attempt in range(MAX_RETRIES + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return _decode(response.read())
            except urllib.error.HTTPError as exc:
                with exc:
                    raw = exc.read()
                    if exc.code == TOO_MANY_REQUESTS and attempt < MAX_RETRIES:
                        self._sleep(retry_wait(attempt, exc.headers.get("Retry-After")))
                        continue
                    try:
                        data = _decode(raw)
                    except ExitMapError:
                        data = {}
                    raise HttpError(exc.code, data) from None
            except (urllib.error.URLError, OSError) as exc:
                # Refused connection, DNS failure, timeout, connection reset…
                raise OfflineError() from exc
        raise AssertionError("unreachable")  # pragma: no cover
