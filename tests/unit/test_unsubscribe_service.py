"""Prepared ``mailto:`` and system opener (spec F5-4, F5-5; plan §4 "Baja")."""

import pytest

from exitmap.app.unsubscribe import SystemOpener, prepared_mailto


@pytest.mark.parametrize(
    "uri, expected",
    [
        ("mailto:baja@shop.es", "mailto:baja@shop.es?subject=unsubscribe"),
        ("mailto:baja@shop.es?subject=baja", "mailto:baja@shop.es?subject=baja"),
        ("mailto:baja@shop.es?Subject=Remove%20me", "mailto:baja@shop.es?Subject=Remove%20me"),
        ("mailto:baja@shop.es?subject=", "mailto:baja@shop.es?subject=unsubscribe"),
        ("mailto:baja@shop.es?body=x", "mailto:baja@shop.es?body=x&subject=unsubscribe"),
    ],
)
def test_prepared_mailto_always_has_a_subject(uri, expected):
    assert prepared_mailto(uri) == expected


class Calls(list):
    def __call__(self, arg):
        self.append(arg)


def test_urls_open_in_the_browser():
    browser = Calls()
    SystemOpener("linux", browser=browser).open_url("https://shop.es")
    assert browser == ["https://shop.es"]


def test_mail_on_linux_uses_xdg_open():
    run, browser = Calls(), Calls()
    SystemOpener("linux", browser=browser, run=run).open_mail("mailto:a@b.es")
    assert run == [["xdg-open", "mailto:a@b.es"]] and browser == []


def test_mail_on_windows_uses_startfile():
    startfile, run = Calls(), Calls()
    SystemOpener("win32", run=run, startfile=startfile).open_mail("mailto:a@b.es")
    assert startfile == ["mailto:a@b.es"] and run == []


def test_mail_elsewhere_falls_back_to_the_browser():
    browser = Calls()
    SystemOpener("darwin", browser=browser, startfile=Calls()).open_mail("mailto:a@b.es")
    assert browser == ["mailto:a@b.es"]
