import pytest

from exitmap.domain.domains import registrable_domain


@pytest.mark.parametrize(
    ("sender", "expected"),
    [
        ("news.amazon.es", "amazon.es"),
        ("mail.bbc.co.uk", "bbc.co.uk"),
        ("amazon.es", "amazon.es"),
        ("a.b.c.example.com", "example.com"),
        ("promo.tienda.com.mx", "tienda.com.mx"),
        ("bbc.co.uk", "bbc.co.uk"),
    ],
)
def test_hostname_is_reduced(sender, expected):
    assert registrable_domain(sender) == expected


def test_uppercase_is_normalised():
    assert registrable_domain("News.AMAZON.Es") == "amazon.es"
    assert registrable_domain("Offers@Mail.BBC.CO.UK") == "bbc.co.uk"


def test_plain_address():
    assert registrable_domain("no-reply@news.amazon.es") == "amazon.es"


@pytest.mark.parametrize(
    "sender",
    [
        "Amazon.es <news@news.amazon.es>",
        '"Amazon, Ofertas" <News@News.Amazon.ES>',
        "news@news.amazon.es (Amazon)",
    ],
)
def test_address_with_display_name(sender):
    assert registrable_domain(sender) == "amazon.es"


def test_trailing_dot_and_spaces():
    assert registrable_domain("  mail.bbc.co.uk. ") == "bbc.co.uk"


def test_no_domain_returns_empty():
    assert registrable_domain("") == ""
    assert registrable_domain("Someone <>") == ""
