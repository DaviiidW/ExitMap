"""Unit tests for reading Gmail ``messages.get`` answers (synthetic JSON, plan §6)."""

import base64

from exitmap.providers.gmail import html_body, message_headers


def b64(text: str, charset: str = "utf-8") -> str:
    return base64.urlsafe_b64encode(text.encode(charset)).decode().rstrip("=")


def test_headers_keep_only_wanted_with_usual_names():
    message = {"payload": {"headers": [
        {"name": "from", "value": "Shop <news@shop.example>"},
        {"name": "Subject", "value": "Hola"},
        {"name": "Received", "value": "by x"},
        {"name": "LIST-UNSUBSCRIBE", "value": "<https://shop.example/u>"},
        {"name": "Subject", "value": "duplicate"},
    ]}}

    assert message_headers(message) == {
        "From": "Shop <news@shop.example>",
        "Subject": "Hola",
        "List-Unsubscribe": "<https://shop.example/u>",
    }


def test_headers_of_empty_answer():
    assert message_headers({}) == {}


def test_html_part_in_nested_multipart():
    message = {"payload": {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("plain")}},
            {"mimeType": "text/html", "body": {"data": b64("<a href='x'>baja</a>")}},
        ]},
        {"mimeType": "application/pdf", "body": {"attachmentId": "att"}},
    ]}}

    assert html_body(message) == "<a href='x'>baja</a>"


def test_html_in_declared_charset():
    part = {
        "mimeType": "text/html",
        "headers": [{"name": "Content-Type", "value": "text/html; charset=ISO-8859-1"}],
        "body": {"data": b64("<p>Suscripción</p>", "latin-1")},
    }
    assert html_body({"payload": part}) == "<p>Suscripción</p>"


def test_message_without_html_or_with_bad_data():
    assert html_body({"payload": {"mimeType": "text/plain", "body": {"data": b64("x")}}}) == ""
    assert html_body({"payload": {"mimeType": "text/html", "body": {"data": "@@@"}}}) == ""
    assert html_body({"payload": {"mimeType": "text/html", "body": {}}}) == ""
