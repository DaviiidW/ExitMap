"""Test doubles shared by the test suite."""

import json
import threading
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from pathlib import Path

from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, PasswordDeleteError

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


class ControlledMailProvider(FakeMailProvider):
    """``FakeMailProvider`` that can pause or fail while reading headers.

    Before reading the headers of message number ``pause_at`` (1-based) it sets
    ``paused`` and waits for ``resume``; at message number ``fail_at`` it raises ``error``.
    """

    def __init__(
        self,
        email: str,
        pause_at: int | None = None,
        fail_at: int | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(email)
        self.pause_at = pause_at
        self.fail_at = fail_at
        self.error = error
        self.paused = threading.Event()
        self.resume = threading.Event()
        self.headers_read = 0

    def get_headers(self, message_id: str) -> Mapping[str, str]:
        self.headers_read += 1
        if self.headers_read == self.pause_at:
            self.paused.set()
            self.resume.wait(timeout=5)
        if self.headers_read == self.fail_at:
            raise self.error
        return super().get_headers(message_id)


class FakeKeyring(KeyringBackend):
    """In-memory ``keyring`` backend, so tests never touch the real system keyring."""

    priority = 1

    def __init__(self, fail: bool = False) -> None:
        super().__init__()
        self.passwords: dict[tuple[str, str], str] = {}
        self.fail = fail

    def _check(self) -> None:
        if self.fail:
            raise KeyringError("keyring locked")

    def get_password(self, service: str, username: str) -> str | None:
        self._check()
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._check()
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._check()
        if (service, username) not in self.passwords:
            raise PasswordDeleteError("not found")
        del self.passwords[(service, username)]
