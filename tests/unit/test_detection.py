import json

import pytest

from exitmap.domain.detection import detect, load_rules, normalise_subject
from exitmap.domain.models import RelationType


@pytest.fixture
def rules(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            {
                "registered": [r"\bwelcome\b", r"\bverifica tu cuenta\b"],
                "access": [r"\bnew app connected\b", r"\bnuevo inicio de sesion\b"],
            }
        ),
        encoding="utf-8",
    )
    return load_rules(path)


def test_registered_by_subject(rules):
    assert detect({"From": "hi@shop.com", "Subject": "Welcome to Shop"}, rules) == {
        RelationType.REGISTERED
    }


def test_subscription_by_list_unsubscribe(rules):
    headers = {
        "From": "news@shop.com",
        "Subject": "Ofertas de la semana",
        "List-Unsubscribe": "<https://shop.com/unsub>",
    }
    assert detect(headers, rules) == {RelationType.SUBSCRIPTION}


def test_access_by_subject(rules):
    assert detect({"Subject": "New app connected to your account"}, rules) == {
        RelationType.ACCESS
    }


def test_combination_of_types(rules):
    headers = {
        "Subject": "Welcome! New app connected",
        "List-Unsubscribe": "<mailto:unsub@shop.com>",
    }
    assert detect(headers, rules) == {
        RelationType.REGISTERED,
        RelationType.SUBSCRIPTION,
        RelationType.ACCESS,
    }


def test_personal_email_has_no_type(rules):
    headers = {"From": "Ana <ana@gmail.com>", "Subject": "¿Quedamos el sábado?"}
    assert detect(headers, rules) == set()


def test_empty_list_unsubscribe_is_ignored(rules):
    assert detect({"Subject": "Hola", "List-Unsubscribe": "  "}, rules) == set()


def test_header_names_are_case_insensitive(rules):
    headers = {"SUBJECT": "WELCOME", "list-unsubscribe": "<https://shop.com/u>"}
    assert detect(headers, rules) == {RelationType.REGISTERED, RelationType.SUBSCRIPTION}


def test_accents_are_ignored(rules):
    assert detect({"Subject": "Nuevo inicio de sesión en tu cuenta"}, rules) == {
        RelationType.ACCESS
    }


def test_missing_headers(rules):
    assert detect({}, rules) == set()


def test_normalise_subject_decodes_mime_words():
    assert normalise_subject("=?utf-8?q?Restablece_tu_contrase=C3=B1a?=") == (
        "restablece tu contrasena"
    )


def test_normalise_subject_keeps_plain_text():
    assert normalise_subject("Verifica TU Cuenta") == "verifica tu cuenta"


def test_default_rules_are_used():
    assert detect({"Subject": "Welcome to Shop"}) == {RelationType.REGISTERED}
