import json

import pytest

from exitmap.domain.catalog import CatalogEntry, load_catalog
from exitmap.errors import CatalogError


def write(tmp_path, content):
    path = tmp_path / "catalog.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), "utf-8")
    return path


@pytest.fixture
def catalog(tmp_path):
    return load_catalog(
        write(
            tmp_path,
            {
                "services": {
                    "shop.com": {
                        "name": "Shop",
                        "manage_url": "https://shop.com/account",
                        "unsubscribe_url": "https://shop.com/emails",
                    },
                    "Blog.ES": {"name": "Blog", "manage_url": "https://blog.es/me"},
                }
            },
        )
    )


def test_load_and_lookup(catalog):
    assert len(catalog) == 2
    assert catalog.lookup("shop.com") == CatalogEntry(
        "Shop", "https://shop.com/account", "https://shop.com/emails"
    )


def test_unsubscribe_url_is_optional(catalog):
    assert catalog.lookup("blog.es").unsubscribe_url is None


def test_lookup_ignores_case_and_spaces(catalog):
    assert catalog.lookup("  SHOP.com. ").name == "Shop"
    assert catalog.lookup("blog.es").name == "Blog"


def test_unknown_domain(catalog):
    assert catalog.lookup("unknown.org") is None
    assert catalog.lookup("") is None


def test_missing_file(tmp_path):
    with pytest.raises(CatalogError) as info:
        load_catalog(tmp_path / "nope.json")
    assert "catálogo" in info.value.user_message


def test_invalid_json(tmp_path):
    with pytest.raises(CatalogError):
        load_catalog(write(tmp_path, "{not json"))


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"services": []},
        {"services": {"shop.com": "Shop"}},
        {"services": {"shop.com": {"manage_url": "https://shop.com"}}},
        {"services": {"shop.com": {"name": " ", "manage_url": "https://shop.com"}}},
        {"services": {"shop.com": {"name": "Shop"}}},
        {"services": {"shop.com": {"name": "Shop", "manage_url": "http://shop.com"}}},
        {
            "services": {
                "shop.com": {
                    "name": "Shop",
                    "manage_url": "https://shop.com",
                    "unsubscribe_url": "javascript:alert(1)",
                }
            }
        },
    ],
)
def test_malformed_structure(tmp_path, data):
    with pytest.raises(CatalogError):
        load_catalog(write(tmp_path, data))
