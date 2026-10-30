"""``List-Unsubscribe`` / ``List-Unsubscribe-Post`` → unsubscribe method (plan §4 "Baja", spec F5).

- ``https`` URI + ``List-Unsubscribe-Post: List-Unsubscribe=One-Click`` → one-click POST
  (RFC 8058).
- ``https`` URI only → open it in the browser.
- ``mailto:`` URI only → prepare an email in the user's mail program.

The header is a comma separated list of URIs in angle brackets (RFC 2369). Entries that are
not well formed are ignored; if none is usable there is no unsubscribe method.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from exitmap.domain.models import UnsubscribeMethod

ONE_CLICK_VALUE = "list-unsubscribe=one-click"

_URI_IN_BRACKETS = re.compile(r"<([^<>]*)>")


@dataclass(frozen=True)
class UnsubscribeOption:
    """How to unsubscribe and where to (URL or ``mailto:`` URI)."""

    method: UnsubscribeMethod
    target: str


def _uris(list_unsubscribe: str) -> list[str]:
    uris = []
    for entry in list_unsubscribe.split(","):
        match = _URI_IN_BRACKETS.fullmatch(entry.strip())
        if match:
            uris.append("".join(match.group(1).split()))  # drop folding whitespace
    return uris


def _is_https(uri: str) -> bool:
    parts = urlsplit(uri)
    return parts.scheme.lower() == "https" and bool(parts.hostname)


def _is_mailto(uri: str) -> bool:
    parts = urlsplit(uri)
    return parts.scheme.lower() == "mailto" and "@" in parts.path


def parse_unsubscribe(
    list_unsubscribe: str | None, list_unsubscribe_post: str | None = None
) -> UnsubscribeOption | None:
    """Return the unsubscribe method and target, or ``None`` if the header gives none.

    When both ``https`` and ``mailto:`` are offered, the web link is preferred.
    """
    uris = _uris(list_unsubscribe or "")
    https = next((u for u in uris if _is_https(u)), None)
    if https:
        one_click = (list_unsubscribe_post or "").strip().lower() == ONE_CLICK_VALUE
        method = UnsubscribeMethod.ONE_CLICK if one_click else UnsubscribeMethod.WEB
        return UnsubscribeOption(method, https)
    mailto = next((u for u in uris if _is_mailto(u)), None)
    if mailto:
        return UnsubscribeOption(UnsubscribeMethod.MAILTO, mailto)
    return None
