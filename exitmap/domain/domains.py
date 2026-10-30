"""Sender address → registrable domain (plan §5, spec §3 "Servicio").

The registrable domain is approximated: the last two labels, or the last three when
the last two form a known compound suffix. The list is short on purpose and can be
extended (plan §8).
"""

from email.utils import parseaddr

COMPOUND_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.es",
        "org.es",
        "com.mx",
        "com.br",
        "com.ar",
        "com.au",
        "co.jp",
        "co.nz",
        "co.za",
        "co.in",
        "com.tr",
    }
)


def registrable_domain(sender: str) -> str:
    """Return the registrable domain of a ``From`` value, address or hostname.

    Examples: ``"Amazon <news@News.Amazon.es>"`` → ``"amazon.es"``,
    ``"mail.bbc.co.uk"`` → ``"bbc.co.uk"``. Returns ``""`` if no domain is found.
    """
    _, address = parseaddr(sender)
    host = address.rpartition("@")[2]
    labels = [label for label in host.strip().strip(".").lower().split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in COMPOUND_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])
