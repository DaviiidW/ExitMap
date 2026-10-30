import logging
import sys

import pytest

from exitmap.logging_setup import REDACTED, SensitiveDataFilter, redact


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Authorization: Bearer abc.DEF-123", "abc.DEF-123"),
        ("access_token=ya29.a0AfH6SM", "a0AfH6SM"),
        ('{"refresh_token": "1//0gXyZ-secret"}', "0gXyZ-secret"),
        ("client_secret: GOCSPX-s3cr3t", "GOCSPX-s3cr3t"),
        ("password=hunter2", "hunter2"),
        ("token ya29.a0Ab-cd.ef in transit", "ya29.a0Ab-cd.ef"),
        ("stored 1//0abcDEF for later", "1//0abcDEF"),
        ("id eyJhbGciOi.eyJzdWIiOi.SflKxwRJ end", "eyJhbGciOi.eyJzdWIiOi.SflKxwRJ"),
        ("redirect /?code=4/0AY0e-g7&state=xyz", "4/0AY0e-g7"),
        ("from Ana <ana.lopez+news@example.co.uk>", "ana.lopez+news@example.co.uk"),
        ("subject=Tu factura de octubre", "Tu factura de octubre"),
        ("Asunto: Restablece tu contraseña", "Restablece tu contraseña"),
        ('{"body": "Hola Ana, tu pedido 123"}', "Hola Ana, tu pedido 123"),
        ("cuerpo=Querido cliente", "Querido cliente"),
    ],
)
def test_redact_removes_secret(text, secret):
    result = redact(text)

    assert secret not in result
    assert REDACTED in result


def test_redact_only_affects_line_of_content_field():
    result = redact("subject=Oferta\nmessages=42")

    assert "Oferta" not in result
    assert "messages=42" in result


@pytest.mark.parametrize(
    "text",
    [
        "Analysis finished: 120 messages, 15 services",
        "HTTP status code: 429, retrying in 2 s",
        "Domain amazon.es matched catalog entry",
    ],
)
def test_redact_keeps_harmless_text(text):
    assert redact(text) == text


def _record(msg, args=(), exc_info=None, stack_info=None):
    return logging.LogRecord(
        "exitmap.test", logging.INFO, __file__, 1, msg, args, exc_info, sinfo=stack_info
    )


def test_filter_redacts_formatting_args_and_keeps_record():
    record = _record("Message from %s with token=%s", ("ana@example.com", "abc123"))

    assert SensitiveDataFilter().filter(record) is True
    assert record.getMessage() == f"Message from {REDACTED} with token={REDACTED}"


def test_filter_redacts_traceback_and_stack():
    try:
        raise ValueError("refresh_token=1//secret-xyz for ana@example.com")
    except ValueError:
        record = _record("Refresh failed", exc_info=sys.exc_info(), stack_info="at ana@example.com")

    SensitiveDataFilter().filter(record)
    output = logging.Formatter().format(record)

    assert "ValueError" in output
    assert "secret-xyz" not in output
    assert "ana@example.com" not in output


def test_filter_redacts_cached_exc_text():
    record = _record("Error")
    record.exc_text = "Traceback: Bearer leaked-token"

    SensitiveDataFilter().filter(record)

    assert "leaked-token" not in record.exc_text
