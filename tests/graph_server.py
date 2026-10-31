"""Local server that imitates the parts of Microsoft Graph that ExitMap uses (plan §6)."""

import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime

from local_server import Reply, Request

ACCESS_TOKEN = "graph-access-token"
FOLDER_IDS = {
    "inbox": "AAMk-inbox",
    "archive": "AAMk-archive",
    "sentitems": "AAMk-sent",
    "drafts": "AAMk-drafts",
    "junkemail": "AAMk-junk",
    "deleteditems": "AAMk-deleted",
}


@dataclass
class GraphMessage:
    id: str
    received: str  # ISO 8601 UTC, as Graph returns it
    folder: str = "inbox"
    headers: dict[str, str] = field(default_factory=dict)
    html: str = ""
    content_type: str = "html"


class FakeGraph:
    """``handler`` answers like Graph; ``page_size`` overrides ``$top`` to test pages."""

    def __init__(self, messages: list[GraphMessage], page_size: int | None = None):
        self.messages = messages
        self.page_size = page_size
        self.base_url = ""  # set by the test, needed for ``@odata.nextLink``

    def handler(self, request: Request) -> Reply:
        if request.headers.get("Authorization") != f"Bearer {ACCESS_TOKEN}":
            return Reply(401, data={"error": {"code": "InvalidAuthenticationToken"}})
        folder = re.fullmatch(r"/me/mailFolders/(\w+)", request.path)
        if folder:
            return Reply(data={"id": FOLDER_IDS[folder.group(1)], "displayName": folder.group(1)})
        if request.path == "/me/messages":
            return self._list(request)
        message = re.fullmatch(r"/me/messages/([\w-]+)", request.path)
        if message:
            return self._get(message.group(1), request)
        return Reply(404, data={"error": {"code": "ErrorItemNotFound"}})

    def _matches(self, message: GraphMessage, condition: str) -> bool:
        received = datetime.fromisoformat(message.received)
        for op, value in re.findall(r"receivedDateTime (ge|lt) (\S+)", condition):
            moment = datetime.fromisoformat(value)
            if op == "ge" and received < moment or op == "lt" and received >= moment:
                return False
        return True

    def _fields(self, message: GraphMessage, select: list[str]) -> dict:
        item: dict = {"id": message.id}
        if "parentFolderId" in select:
            item["parentFolderId"] = FOLDER_IDS[message.folder]
        if "receivedDateTime" in select:
            item["receivedDateTime"] = message.received
        if "internetMessageHeaders" in select:
            item["internetMessageHeaders"] = [
                {"name": n, "value": v} for n, v in message.headers.items()
            ]
        if "body" in select:
            item["body"] = {"contentType": message.content_type, "content": message.html}
        return item

    def _list(self, request: Request) -> Reply:
        select = (request.param("$select") or "").split(",")
        found = [m for m in self.messages if self._matches(m, request.param("$filter") or "")]
        size = self.page_size or int(request.param("$top") or 10)
        skip = int(request.param("$skip") or 0)
        data: dict = {"value": [self._fields(m, select) for m in found[skip : skip + size]]}
        if skip + size < len(found):
            query = {k: v[0] for k, v in request.query.items()}
            query["$skip"] = str(skip + size)
            data["@odata.nextLink"] = (
                f"{self.base_url}/me/messages?{urllib.parse.urlencode(query)}"
            )
        return Reply(data=data)

    def _get(self, message_id: str, request: Request) -> Reply:
        message = next((m for m in self.messages if m.id == message_id), None)
        if message is None:
            return Reply(404, data={"error": {"code": "ErrorItemNotFound"}})
        return Reply(data=self._fields(message, (request.param("$select") or "").split(",")))
