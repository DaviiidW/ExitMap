"""The real ``data/catalog.json`` (plan §4 "Catálogo")."""

import pytest

from exitmap.domain.catalog import CATALOG_PATH, default_catalog, load_catalog
from exitmap.domain.domains import registrable_domain

CATALOG = load_catalog(CATALOG_PATH)


@pytest.mark.parametrize(
    ("domain", "name"),
    [
        ("google.com", "Google"),
        ("microsoft.com", "Microsoft"),
        ("amazon.es", "Amazon"),
        ("netflix.com", "Netflix"),
        ("spotify.com", "Spotify"),
        ("facebook.com", "Facebook"),
        ("instagram.com", "Instagram"),
        ("linkedin.com", "LinkedIn"),
        ("x.com", "X"),
        ("paypal.com", "PayPal"),
    ],
)
def test_initial_services_are_listed(domain, name):
    entry = CATALOG.lookup(domain)
    assert entry is not None and entry.name == name
    assert entry.manage_url.startswith("https://")


@pytest.mark.parametrize(
    ("sender", "name"),
    [
        ("Facebook <notification@facebookmail.com>", "Facebook"),
        ("Amazon.es <store-news@amazon.es>", "Amazon"),
        ("Instagram <security@mail.instagram.com>", "Instagram"),
        ("Microsoft <account-security-noreply@accountprotection.microsoft.com>", "Microsoft"),
    ],
)
def test_lookup_from_sender_address(sender, name):
    assert CATALOG.lookup(registrable_domain(sender)).name == name


def test_default_catalog_is_the_real_file():
    assert default_catalog().lookup("netflix.com").name == "Netflix"
