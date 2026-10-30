"""``List-Unsubscribe`` read from synthetic RFC 822 messages (plan §4 "Baja")."""

from email import message_from_string, policy

from exitmap.domain.models import UnsubscribeMethod
from exitmap.domain.unsubscribe import parse_unsubscribe

ONE_CLICK_EMAIL = """\
From: Shop News <news@mail.shop.com>
To: user@example.com
Subject: Ofertas de la semana
List-Unsubscribe: <mailto:unsub@shop.com?subject=unsubscribe>,
 <https://shop.com/unsub?id=abc>
List-Unsubscribe-Post: List-Unsubscribe=One-Click

Hola
"""

MAILTO_EMAIL = """\
From: Club <club@example.org>
Subject: Boletín
List-Unsubscribe: <mailto:leave@example.org>

Hola
"""

PERSONAL_EMAIL = """\
From: Ana <ana@example.com>
Subject: Hola

Hola
"""


def _option(raw):
    message = message_from_string(raw, policy=policy.default)
    return parse_unsubscribe(
        message.get("List-Unsubscribe"), message.get("List-Unsubscribe-Post")
    )


def test_folded_header_with_post_is_one_click():
    option = _option(ONE_CLICK_EMAIL)
    assert option.method is UnsubscribeMethod.ONE_CLICK
    assert option.target == "https://shop.com/unsub?id=abc"


def test_mailto_email():
    option = _option(MAILTO_EMAIL)
    assert option.method is UnsubscribeMethod.MAILTO
    assert option.target == "mailto:leave@example.org"


def test_email_without_header():
    assert _option(PERSONAL_EMAIL) is None
