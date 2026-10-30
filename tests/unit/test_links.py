import pytest

from exitmap.domain.catalog import Catalog, CatalogEntry
from exitmap.domain.links import (
    Link,
    ManagementLink,
    email_management_link,
    extract_links,
    management_link,
)
from exitmap.domain.models import LinkSource

EMPTY_CATALOG = Catalog({})
CATALOG = Catalog({"shop.com": CatalogEntry("Shop", "https://shop.com/catalog-account")})

SHOP_HTML = """
<html><body>
  <a href="https://shop.com/products/42">Ver oferta</a>
  <a href="https://twitter.com/shop/settings">Síguenos</a>
  <a href="https://mail.shop.com/u/abc">Gestionar mis preferencias</a>
  <a href="https://shop.com/account">Mi cuenta</a>
</body></html>
"""


def test_extract_links_in_order_with_text():
    html = '<p><a href=" https://a.com/x ">Hola &amp;\n  adiós</a> <a>sin href</a>'
    html += '<a href="https://b.com"><b>Negrita</b></a></p>'
    assert extract_links(html) == [
        Link("https://a.com/x", "Hola & adiós"),
        Link("https://b.com", "Negrita"),
    ]


def test_extract_links_unescapes_href():
    assert extract_links('<a href="https://a.com/?a=1&amp;b=2">x</a>')[0].url == (
        "https://a.com/?a=1&b=2"
    )


def test_extract_links_unclosed_anchor():
    assert extract_links('<a href="https://a.com/settings">Ajustes') == [
        Link("https://a.com/settings", "Ajustes")
    ]


@pytest.mark.parametrize("html", ["", "<p>Hola, sin enlaces</p>", "texto plano", "<a>vacío</a>"])
def test_extract_links_without_links(html):
    assert extract_links(html) == []


def test_catalog_has_priority():
    assert management_link("shop.com", [SHOP_HTML], CATALOG) == ManagementLink(
        "https://shop.com/catalog-account", LinkSource.CATALOG
    )


def test_catalog_lookup_ignores_case():
    assert management_link("Shop.COM", [], CATALOG).source is LinkSource.CATALOG


def test_email_link_when_not_in_catalog():
    # The first link of the service's domain with a keyword (text "preferencias").
    assert management_link("shop.com", [SHOP_HTML], EMPTY_CATALOG) == ManagementLink(
        "https://mail.shop.com/u/abc", LinkSource.EMAIL
    )


def test_homepage_when_no_link_in_emails():
    html = '<a href="https://shop.com/products/42">Ver oferta</a>'
    assert management_link("shop.com", [html], EMPTY_CATALOG) == ManagementLink(
        "https://shop.com/", LinkSource.HOMEPAGE
    )


def test_homepage_without_bodies():
    assert management_link("shop.com", catalog=EMPTY_CATALOG) == ManagementLink(
        "https://shop.com/", LinkSource.HOMEPAGE
    )


def test_uses_default_catalog():
    assert management_link("netflix.com").source is LinkSource.CATALOG


@pytest.mark.parametrize(
    "html",
    [
        '<a href="https://shop.com/settings/notifications">Aquí</a>',
        '<a href="https://shop.com/x?action=unsubscribe">Aquí</a>',
        '<a href="https://shop.com/x">Configuración</a>',
        '<a href="https://shop.com/x">Darse de BAJA</a>',
        '<a href="https://shop.com/x">Privacy policy</a>',
        '<a href="https://www.shop.com/my-account">x</a>',
    ],
)
def test_keyword_in_url_or_text(html):
    assert email_management_link("shop.com", [html]) is not None


@pytest.mark.parametrize(
    "html",
    [
        '<a href="http://shop.com/account">Mi cuenta</a>',  # not https
        '<a href="https://other.com/account">Mi cuenta</a>',  # other domain
        '<a href="https://shop.com.evil.com/account">Mi cuenta</a>',
        '<a href="/account">Mi cuenta</a>',  # relative
        '<a href="mailto:help@shop.com">Cuenta</a>',
        '<a href="https://shop.com/trabajar">Trabaja con nosotros</a>',  # no whole word
        '<a href="https://shop.com/products">Ver</a>',
    ],
)
def test_links_that_are_not_management_links(html):
    assert email_management_link("shop.com", [html]) is None


def test_searches_following_bodies():
    bodies = ["<p>sin enlaces</p>", '<a href="https://shop.com/account">Cuenta</a>']
    assert email_management_link("shop.com", bodies) == "https://shop.com/account"
