"""Management link from synthetic RFC 822 messages and the real catalog (spec F4-3, F4-4)."""

from email import message_from_string, policy

from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.links import management_link
from exitmap.domain.models import LinkSource

CATALOG = load_catalog(CATALOG_PATH)

SHOP_EMAIL = """\
From: Tienda <news@mail.tienda-ejemplo.es>
Subject: Ofertas de la semana
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="b"

--b
Content-Type: text/plain; charset=utf-8

Ofertas: https://tienda-ejemplo.es/ofertas

--b
Content-Type: text/html; charset=utf-8
Content-Transfer-Encoding: quoted-printable

<html><body>
<a href=3D"https://tienda-ejemplo.es/ofertas">Ver ofertas</a>
<a href=3D"https://tienda-ejemplo.es/cuenta/preferencias?u=3D1&amp;t=3D2">Gestiona tus =
preferencias</a>
</body></html>

--b--
"""

NETFLIX_EMAIL = """\
From: Netflix <info@mailer.netflix.com>
Subject: Novedades
Content-Type: text/html; charset=utf-8

<a href="https://www.netflix.com/browse">Ver</a>
<a href="https://www.netflix.com/account/other">Cuenta</a>
"""

PLAIN_EMAIL = """\
From: Club <club@club-ejemplo.org>
Subject: Bienvenido
Content-Type: text/plain; charset=utf-8

Hola, gracias por registrarte.
"""


def _html_bodies(*raws):
    bodies = []
    for raw in raws:
        message = message_from_string(raw, policy=policy.default)
        part = message.get_body(preferencelist=("html",))
        if part is not None:
            bodies.append(part.get_content())
    return bodies


def test_email_link_from_multipart_message():
    link = management_link("tienda-ejemplo.es", _html_bodies(SHOP_EMAIL), CATALOG)
    assert link.source is LinkSource.EMAIL
    assert link.url == "https://tienda-ejemplo.es/cuenta/preferencias?u=1&t=2"


def test_catalog_wins_over_email_link():
    link = management_link("netflix.com", _html_bodies(NETFLIX_EMAIL), CATALOG)
    assert link.source is LinkSource.CATALOG
    assert link.url == CATALOG.lookup("netflix.com").manage_url


def test_plain_text_email_falls_back_to_homepage():
    link = management_link("club-ejemplo.org", _html_bodies(PLAIN_EMAIL), CATALOG)
    assert (link.url, link.source) == ("https://club-ejemplo.org/", LinkSource.HOMEPAGE)
