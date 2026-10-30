"""Catalog of known services, indexed by registrable domain (plan §4 "Catálogo").

The catalog lives in ``data/catalog.json`` and is updated with ``git pull``; it is never
downloaded (constitution 6). A missing or malformed file raises ``CatalogError``.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from exitmap.errors import CatalogError

CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "catalog.json"


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    manage_url: str
    unsubscribe_url: str | None = None


class Catalog:
    def __init__(self, entries: Mapping[str, CatalogEntry]) -> None:
        self._entries = {domain.lower(): entry for domain, entry in entries.items()}

    def lookup(self, domain: str) -> CatalogEntry | None:
        """Return the entry of a registrable domain, or ``None`` if it is not listed."""
        return self._entries.get(domain.strip().strip(".").lower())

    def __len__(self) -> int:
        return len(self._entries)


def _is_https_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def _parse_entry(raw: object) -> CatalogEntry:
    if not isinstance(raw, dict):
        raise ValueError("entry is not an object")
    name = raw.get("name")
    manage_url = raw.get("manage_url")
    unsubscribe_url = raw.get("unsubscribe_url")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("missing name")
    if not _is_https_url(manage_url):
        raise ValueError("invalid manage_url")
    if unsubscribe_url is not None and not _is_https_url(unsubscribe_url):
        raise ValueError("invalid unsubscribe_url")
    return CatalogEntry(name.strip(), manage_url, unsubscribe_url)


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    """Read a catalog file; raise ``CatalogError`` if it is missing or malformed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        services = data["services"]
        if not isinstance(services, dict):
            raise ValueError("services is not an object")
        return Catalog({domain: _parse_entry(raw) for domain, raw in services.items()})
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise CatalogError() from exc


@cache
def default_catalog() -> Catalog:
    return load_catalog()
