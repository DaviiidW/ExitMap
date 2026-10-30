"""Management link of a service (spec F4-3, F4-4; plan §4, §5).

Order: 1) app catalog, 2) a link in the service's emails, 3) the domain's homepage.

A link in an email counts as a management link when it is ``https``, belongs to the
service's registrable domain and its text or URL contains a management keyword (account,
settings, preferences, privacy, unsubscribe…). The first match wins.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

from exitmap.domain.catalog import Catalog, default_catalog
from exitmap.domain.domains import registrable_domain
from exitmap.domain.models import LinkSource

MANAGEMENT_KEYWORDS = (
    "account",
    "accounts",
    "myaccount",
    "settings",
    "preferences",
    "privacy",
    "unsubscribe",
    "subscription",
    "subscriptions",
    "manage",
    "cuenta",
    "ajustes",
    "configuracion",
    "preferencias",
    "privacidad",
    "baja",
    "suscripcion",
    "suscripciones",
    "gestionar",
)

_KEYWORD = re.compile(r"\b(" + "|".join(MANAGEMENT_KEYWORDS) + r")\b")


@dataclass(frozen=True)
class Link:
    """An ``<a href>`` of an HTML body and its visible text."""

    url: str
    text: str


@dataclass(frozen=True)
class ManagementLink:
    url: str
    source: LinkSource


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        self._close_anchor()
        href = dict(attrs).get("href")
        self._href = href.strip() if href else None
        self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._close_anchor()

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def close(self) -> None:
        super().close()
        self._close_anchor()

    def _close_anchor(self) -> None:
        if self._href:
            self.links.append(Link(self._href, " ".join("".join(self._text).split())))
        self._href = None
        self._text = []


def extract_links(html: str) -> list[Link]:
    """Return the ``<a href>`` links of an HTML body, in document order."""
    parser = _AnchorParser()
    parser.feed(html)
    parser.close()
    return parser.links


def _normalise(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _is_management_link(link: Link, domain: str) -> bool:
    parts = urlsplit(link.url)
    if parts.scheme.lower() != "https" or not parts.hostname:
        return False
    if registrable_domain(parts.hostname) != domain:
        return False
    url_words = _normalise(f"{parts.path} {parts.query}")
    return bool(_KEYWORD.search(_normalise(link.text)) or _KEYWORD.search(url_words))


def email_management_link(domain: str, html_bodies: Iterable[str]) -> str | None:
    """Return the first management link found in the service's HTML bodies, if any."""
    domain = domain.strip().strip(".").lower()
    for html in html_bodies:
        for link in extract_links(html):
            if _is_management_link(link, domain):
                return link.url
    return None


def management_link(
    domain: str, html_bodies: Iterable[str] = (), catalog: Catalog | None = None
) -> ManagementLink:
    """Return the management link of a service and where it comes from (F4-3, F4-4)."""
    domain = domain.strip().strip(".").lower()
    entry = (catalog or default_catalog()).lookup(domain)
    if entry:
        return ManagementLink(entry.manage_url, LinkSource.CATALOG)
    url = email_management_link(domain, html_bodies)
    if url:
        return ManagementLink(url, LinkSource.EMAIL)
    return ManagementLink(f"https://{domain}/", LinkSource.HOMEPAGE)
