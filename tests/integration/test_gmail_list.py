"""Gmail listing against a local server that imitates Gmail (plan §4; spec F2-1, F2-3)."""

from datetime import UTC, datetime, timedelta

import pytest
from gmail_server import ACCESS_TOKEN, FakeGmail, GmailMessage
from local_server import LocalServer, Reply

from exitmap.providers.base import Folders, Period
from exitmap.providers.gmail import GmailProvider, GoogleEndpoints
from exitmap.providers.oauth import Tokens

JAN = int(datetime(2026, 1, 15, tzinfo=UTC).timestamp())
JUN = int(datetime(2026, 6, 15, tzinfo=UTC).timestamp())

MESSAGES = [
    GmailMessage("inbox1", JAN),
    GmailMessage("archived", JUN, labels=()),
    GmailMessage("inbox2", JUN),
    GmailMessage("spam", JUN, labels=("SPAM",)),
    GmailMessage("trash", JAN, labels=("TRASH",)),
    GmailMessage("sent", JUN, labels=("SENT",)),
    GmailMessage("draft", JUN, labels=("DRAFT",)),
]


def endpoints(url: str) -> GoogleEndpoints:
    return GoogleEndpoints(api=url + "/api", auth=url + "/auth", token=url + "/token",
                           revoke=url + "/revoke")


def provider(url: str, access_token: str = ACCESS_TOKEN) -> GmailProvider:
    tokens = Tokens(access_token, "rt", datetime.now(UTC) + timedelta(hours=1))
    return GmailProvider("cid", "secret", tokens, endpoints=endpoints(url))


@pytest.fixture
def gmail():
    fake = FakeGmail(MESSAGES, page_size=2)
    with LocalServer(fake.handler) as server:
        yield fake, server


def test_pages_are_followed_and_the_total_is_exact(gmail):
    fake, server = gmail
    ids = provider(server.url).list_message_ids(Period(), Folders())

    assert ids == ["inbox1", "archived", "inbox2"]
    assert len(server.requests) == 2
    assert server.requests[1].param("pageToken") == "2"
    assert server.requests[0].param("maxResults") == "500"


def test_period_filters_by_date(gmail):
    _, server = gmail
    start = datetime(2026, 3, 1, tzinfo=UTC)

    assert provider(server.url).list_message_ids(Period(start=start), Folders()) == [
        "archived", "inbox2"
    ]
    assert provider(server.url).list_message_ids(Period(end=start), Folders()) == ["inbox1"]


@pytest.mark.parametrize(
    ("folders", "extra"),
    [
        (Folders(include_spam=True), ["spam"]),
        (Folders(include_trash=True), ["trash"]),
        (Folders(include_spam=True, include_trash=True), ["spam", "trash"]),
    ],
)
def test_spam_and_trash_only_when_chosen(gmail, folders, extra):
    _, server = gmail
    ids = provider(server.url).list_message_ids(Period(), folders)
    assert sorted(ids) == sorted(["inbox1", "archived", "inbox2", *extra])


def test_empty_mailbox():
    with LocalServer(FakeGmail([]).handler) as server:
        assert provider(server.url).list_message_ids(Period(), Folders()) == []


def test_expired_access_token_is_refreshed_with_the_client_secret():
    fake = FakeGmail(MESSAGES)

    def handler(request):
        if request.path == "/token":
            return Reply(data={"access_token": ACCESS_TOKEN, "expires_in": 3600})
        return fake.handler(request)

    with LocalServer(handler) as server:
        gmail_provider = provider(server.url, access_token="stale")
        ids = gmail_provider.list_message_ids(Period(), Folders())

    assert len(ids) == 3
    token_request = next(r for r in server.requests if r.path == "/token")
    assert token_request.form["client_secret"] == "secret"
    assert gmail_provider.session.tokens.access_token == ACCESS_TOKEN
