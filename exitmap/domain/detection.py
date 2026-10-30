"""Email headers → relation types (plan §5).

- Commercial subscription: the email has a ``List-Unsubscribe`` header.
- Registered account / access granted: the subject matches a pattern of
  ``data/rules.json``.

An email that matches no rule gives no relation type, so personal email never creates a
service.
"""

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from email.header import decode_header, make_header
from functools import cache
from pathlib import Path

from exitmap.domain.models import RelationType

RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "rules.json"


@dataclass(frozen=True)
class Rules:
    """Compiled subject patterns per relation type."""

    registered: tuple[re.Pattern[str], ...]
    access: tuple[re.Pattern[str], ...]


def load_rules(path: Path = RULES_PATH) -> Rules:
    """Read and compile the subject patterns of a rules file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return Rules(
        registered=tuple(re.compile(p, re.IGNORECASE) for p in data["registered"]),
        access=tuple(re.compile(p, re.IGNORECASE) for p in data["access"]),
    )


@cache
def default_rules() -> Rules:
    return load_rules()


def normalise_subject(subject: str) -> str:
    """Decode MIME encoded words, lowercase and strip accents (``Contraseña`` → ``contrasena``)."""
    try:
        subject = str(make_header(decode_header(subject)))
    except (ValueError, LookupError):
        pass
    decomposed = unicodedata.normalize("NFKD", subject.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def detect(headers: Mapping[str, str], rules: Rules | None = None) -> set[RelationType]:
    """Return the relation types an email shows; empty if it matches no rule.

    Header names are matched case-insensitively.
    """
    rules = rules or default_rules()
    by_name = {name.lower(): value for name, value in headers.items()}
    types: set[RelationType] = set()

    if by_name.get("list-unsubscribe", "").strip():
        types.add(RelationType.SUBSCRIPTION)

    subject = normalise_subject(by_name.get("subject", ""))
    if any(p.search(subject) for p in rules.registered):
        types.add(RelationType.REGISTERED)
    if any(p.search(subject) for p in rules.access):
        types.add(RelationType.ACCESS)
    return types
