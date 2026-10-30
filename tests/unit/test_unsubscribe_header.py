import pytest

from exitmap.domain.models import UnsubscribeMethod
from exitmap.domain.unsubscribe import UnsubscribeOption, parse_unsubscribe

ONE_CLICK = "List-Unsubscribe=One-Click"


def test_https_only_is_web():
    assert parse_unsubscribe("<https://shop.com/unsub?u=1>") == UnsubscribeOption(
        UnsubscribeMethod.WEB, "https://shop.com/unsub?u=1"
    )


def test_https_with_post_is_one_click():
    assert parse_unsubscribe("<https://shop.com/unsub>", ONE_CLICK) == UnsubscribeOption(
        UnsubscribeMethod.ONE_CLICK, "https://shop.com/unsub"
    )


def test_post_value_is_case_insensitive():
    option = parse_unsubscribe("<https://shop.com/unsub>", "  list-unsubscribe=one-click ")
    assert option.method is UnsubscribeMethod.ONE_CLICK


def test_other_post_value_is_web():
    option = parse_unsubscribe("<https://shop.com/unsub>", "something-else")
    assert option.method is UnsubscribeMethod.WEB


def test_mailto_only():
    assert parse_unsubscribe("<mailto:unsub@shop.com?subject=unsubscribe>") == (
        UnsubscribeOption(UnsubscribeMethod.MAILTO, "mailto:unsub@shop.com?subject=unsubscribe")
    )


def test_post_without_https_is_still_mailto():
    option = parse_unsubscribe("<mailto:unsub@shop.com>", ONE_CLICK)
    assert option.method is UnsubscribeMethod.MAILTO


@pytest.mark.parametrize(
    "header",
    [
        "<mailto:unsub@shop.com>, <https://shop.com/unsub>",
        "<https://shop.com/unsub>,<mailto:unsub@shop.com>",
    ],
)
def test_both_prefers_https(header):
    assert parse_unsubscribe(header) == UnsubscribeOption(
        UnsubscribeMethod.WEB, "https://shop.com/unsub"
    )


def test_both_with_post_is_one_click():
    option = parse_unsubscribe("<mailto:unsub@shop.com>, <https://shop.com/unsub>", ONE_CLICK)
    assert option == UnsubscribeOption(UnsubscribeMethod.ONE_CLICK, "https://shop.com/unsub")


@pytest.mark.parametrize("header", [None, "", "   "])
def test_absent(header):
    assert parse_unsubscribe(header, ONE_CLICK) is None


@pytest.mark.parametrize(
    "header",
    [
        "https://shop.com/unsub",  # no angle brackets
        "<https://shop.com/unsub",  # unclosed
        "<>",
        "<https://>",  # no host
        "<http://shop.com/unsub>",  # not https
        "<mailto:>",  # no address
        "<ftp://shop.com/unsub>",
        "garbage, <<nested>>",
    ],
)
def test_malformed(header):
    assert parse_unsubscribe(header, ONE_CLICK) is None


def test_malformed_entry_is_skipped():
    option = parse_unsubscribe("broken, <mailto:unsub@shop.com>")
    assert option == UnsubscribeOption(UnsubscribeMethod.MAILTO, "mailto:unsub@shop.com")


def test_folding_whitespace_inside_uri_is_removed():
    option = parse_unsubscribe("<https://shop.com/\r\n unsub>")
    assert option.target == "https://shop.com/unsub"
