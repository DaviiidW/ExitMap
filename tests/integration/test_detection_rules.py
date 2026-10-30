"""Detection with the real ``data/rules.json`` (plan §5)."""

import pytest

from exitmap.domain.detection import RULES_PATH, detect, load_rules
from exitmap.domain.models import RelationType

RULES = load_rules(RULES_PATH)


@pytest.mark.parametrize(
    "subject",
    [
        "Welcome to Netflix",
        "¡Bienvenido a Amazon!",
        "Please verify your email address",
        "Confirma tu cuenta de Spotify",
        "Thanks for signing up",
        "Gracias por registrarte",
        "Reset your password",
        "Restablece tu contraseña",
        "Tu cuenta se ha creado",
    ],
)
def test_registered_subjects(subject):
    assert detect({"Subject": subject}, RULES) == {RelationType.REGISTERED}


@pytest.mark.parametrize(
    "subject",
    [
        "New app connected to your account",
        "Nueva aplicación conectada a tu cuenta",
        "Your new API key",
        "Tu nueva clave de API",
        "New sign-in to your account",
        "Nuevo inicio de sesión en Microsoft",
        "Zapier has been granted access to your account",
        "Integración activada",
    ],
)
def test_access_subjects(subject):
    assert detect({"Subject": subject}, RULES) == {RelationType.ACCESS}


@pytest.mark.parametrize(
    "subject",
    [
        "Re: cena del viernes",
        "Fotos de las vacaciones",
        "Your order has shipped",
        "Factura de octubre",
    ],
)
def test_personal_or_unrelated_subjects(subject):
    assert detect({"Subject": subject}, RULES) == set()


def test_newsletter_with_list_unsubscribe():
    headers = {
        "From": "Spotify <no-reply@news.spotify.com>",
        "Subject": "Novedades para ti",
        "List-Unsubscribe": "<https://spotify.com/unsub>, <mailto:u@spotify.com>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    assert detect(headers, RULES) == {RelationType.SUBSCRIPTION}


def test_welcome_newsletter_is_registered_and_subscription():
    headers = {"Subject": "Welcome to LinkedIn", "List-Unsubscribe": "<https://l.in/u>"}
    assert detect(headers, RULES) == {RelationType.REGISTERED, RelationType.SUBSCRIPTION}
