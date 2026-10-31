"""Local server that imitates the parts of the Gmail API that ExitMap uses (plan §6)."""

import base64
import re
from dataclasses import dataclass, field

from local_server import Reply, Request

ACCESS_TOKEN = "gmail-access-token"


@dataclass
class GmailMessage:
    id: str
    epoch: int
    labels: tuple[str, ...] = ("INBOX",)
    headers: dict[str, str] = field(default_factory=dict)
    html: str = ""


class FakeGmail:
    """``handler`` answers like Gmail; ``page_size`` overrides ``maxResults`` to test pages."""

    def __init__(self, messages: list[GmailMessage], page_size: int | None = None):
        self.messages = messages
        self.page_size = page_size
        self.email = "ana@gmail.com"
        self.revoked: list[str] = []

    def _matches(self, message: GmailMessage, request: Request) -> bool:
        query = request.param("q") or ""
        spam_trash = request.param("includeSpamTrash") == "true"
        labels = set(message.labels)
        if not spam_trash and labels & {"SPAM", "TRASH"}:
            return False
        for name in re.findall(r"-in:(\w+)", query):
            label = {"drafts": "DRAFT"}.get(name, name.upper())
            if label in labels:
                return False
        after = re.search(r"after:(\d+)", query)
        before = re.search(r"before:(\d+)", query)
        if after and message.epoch < int(after.group(1)):
            return False
        if before and message.epoch >= int(before.group(1)):
            return False
        return True

    def handler(self, request: Request) -> Reply:
        if request.path == "/revoke":
            self.revoked.append(request.form.get("token", ""))
            return Reply(200)
        if request.headers.get("Authorization") != f"Bearer {ACCESS_TOKEN}":
            return Reply(401, data={"error": {"code": 401}})
        if request.path == "/api/messages":
            return self._list(request)
        if request.path == "/api/profile":
            return Reply(data={"emailAddress": self.email, "messagesTotal": len(self.messages)})
        match = re.fullmatch(r"/api/messages/(\w+)", request.path)
        if match:
            return self._get(match.group(1), request)
        return Reply(404, data={"error": {"code": 404}})

    def _list(self, request: Request) -> Reply:
        found = [m for m in self.messages if self._matches(m, request)]
        size = self.page_size or int(request.param("maxResults") or 100)
        offset = int(request.param("pageToken") or 0)
        page = found[offset : offset + size]
        data: dict = {"resultSizeEstimate": len(found)}
        if page:
            data["messages"] = [{"id": m.id, "threadId": m.id} for m in page]
        if offset + size < len(found):
            data["nextPageToken"] = str(offset + size)
        return Reply(data=data)

    def _get(self, message_id: str, request: Request) -> Reply:
        message = next((m for m in self.messages if m.id == message_id), None)
        if message is None:
            return Reply(404, data={"error": {"code": 404}})
        fmt = request.param("format")
        wanted = request.query.get("metadataHeaders", [])
        headers = [
            {"name": name, "value": value}
            for name, value in message.headers.items()
            if fmt != "metadata" or name in wanted
        ]
        payload: dict = {"mimeType": "text/plain", "headers": headers}
        if fmt == "full":
            payload = {
                "mimeType": "multipart/alternative",
                "headers": headers,
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("plain text")}},
                    {"mimeType": "text/html", "body": {"data": _b64(message.html)}},
                ],
            }
        return Reply(data={"id": message.id, "labelIds": list(message.labels), "payload": payload})


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")
