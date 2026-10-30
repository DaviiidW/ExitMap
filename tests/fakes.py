"""Test doubles shared by the test suite."""

import json
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from pathlib import Path

from exitmap.domain.models import Provider
from exitmap.providers.base import Folders, Period, RevokeNotSupported

MAILBOX_PATH = Path(__file__).resolve().parent / "fixtures" / "mailbox.json"


class FakeMailProvider:
    """``MailProvider`` backed by one account of a synthetic mailbox file (plan §6).

    The message date comes from its ``Date`` header, as with a real provider.
    """

    def __init__(self, email: str, mailbox_path: Path = MAILBOX_PATH) -> None:
        data = json.loads(mailbox_path.read_text(encoding="utf-8"))
        account = data["accounts"][email]
        self.email = email
        self.provider = Provider(account["provider"])
        self.messages = {m["id"]: m for m in account["messages"]}
        self.authorized = False
        self.revoked = False

    def authorize(self) -> None:
        self.authorized = True

    def account_email(self) -> str:
        return self.email

    def list_message_ids(self, period: Period, folders: Folders) -> list[str]:
        allowed = {"inbox"}
        if folders.include_spam:
            allowed.add("spam")
        if folders.include_trash:
            allowed.add("trash")
        return [
            message_id
            for message_id, message in self.messages.items()
            if message["folder"] in allowed
            and period.contains(parsedate_to_datetime(message["headers"]["Date"]))
        ]

    def get_headers(self, message_id: str) -> Mapping[str, str]:
        return dict(self.messages[message_id]["headers"])

    def get_body(self, message_id: str) -> str:
        return self.messages[message_id]["body"]

    def revoke(self) -> None:
        if self.provider is Provider.OUTLOOK:
            raise RevokeNotSupported()
        self.revoked = True
