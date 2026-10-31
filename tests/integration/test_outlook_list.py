"""Outlook listing against a local server that imitates Graph (plan §4; spec F2-1, F2-3)."""

from datetime import UTC, datetime, timedelta

import pytest
from graph_server import ACCESS_TOKEN, FakeGraph, GraphMessage
from local_server import LocalServer

from exitmap.providers.base import Folders, Period
from exitmap.providers.oauth import Tokens
from exitmap.providers.outlook import MicrosoftEndpoints, OutlookProvider

MESSAGES = [
    GraphMessage("inbox1", "2026-01-15T10:00:00Z"),
    GraphMessage("archived", "2026-06-15T10:00:00Z", folder="archive"),
    GraphMessage("sent", "2026-06-15T10:00:00Z", folder="sentitems"),
    GraphMessage("inbox2", "2026-06-16T10:00:00Z"),
    GraphMessage("draft", "2026-06-16T10:00:00Z", folder="drafts"),
    GraphMessage("junk", "2026-06-17T10:00:00Z", folder="junkemail"),
    GraphMessage("deleted", "2026-01-17T10:00:00Z", folder="deleteditems"),
]


def endpoints(url: str) -> MicrosoftEndpoints:
    return MicrosoftEndpoints(api=url + "/me", auth=url + "/auth", token=url + "/token")


def provider(url: str) -> OutlookProvider:
    tokens = Tokens(ACCESS_TOKEN, "rt", datetime.now(UTC) + timedelta(hours=1))
    return OutlookProvider("cid", tokens, endpoints=endpoints(url))


@pytest.fixture
def graph():
    fake = FakeGraph(MESSAGES, page_size=3)
    with LocalServer(fake.handler) as server:
        fake.base_url = server.url
        yield server


def test_pages_are_followed_and_excluded_folders_dropped(graph):
    ids = provider(graph.url).list_message_ids(Period(), Folders())

    assert ids == ["inbox1", "archived", "inbox2"]
    pages = [r for r in graph.requests if r.path == "/me/messages"]
    assert len(pages) == 3
    assert pages[0].param("$select") == "id,parentFolderId"
    assert pages[0].param("$top") == "100"
    assert pages[1].param("$skip") == "3"


def test_folder_ids_are_looked_up_by_well_known_name(graph):
    provider(graph.url).list_message_ids(Period(), Folders(include_spam=True))

    looked_up = [r.path for r in graph.requests if r.path.startswith("/me/mailFolders/")]
    assert looked_up == ["/me/mailFolders/sentitems", "/me/mailFolders/drafts",
                         "/me/mailFolders/deleteditems"]


def test_period_filters_by_received_date(graph):
    start = datetime(2026, 3, 1, tzinfo=UTC)

    assert provider(graph.url).list_message_ids(Period(start=start), Folders()) == [
        "archived", "inbox2"
    ]
    assert provider(graph.url).list_message_ids(Period(end=start), Folders()) == ["inbox1"]


@pytest.mark.parametrize(
    ("folders", "extra"),
    [
        (Folders(include_spam=True), ["junk"]),
        (Folders(include_trash=True), ["deleted"]),
        (Folders(include_spam=True, include_trash=True), ["junk", "deleted"]),
    ],
)
def test_junk_and_deleted_only_when_chosen(graph, folders, extra):
    ids = provider(graph.url).list_message_ids(Period(), folders)
    assert sorted(ids) == sorted(["inbox1", "archived", "inbox2", *extra])


def test_empty_mailbox():
    fake = FakeGraph([])
    with LocalServer(fake.handler) as server:
        assert provider(server.url).list_message_ids(Period(), Folders()) == []
