"""``MailProvider`` port (plan §2 "Interfaz MailProvider").

Each provider (Gmail, Outlook) implements this protocol and is tested on its own, so the
rest of the app never depends on a concrete provider (constitution 1).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class RevokeNotSupported(Exception):
    """The provider does not let the app revoke its own permission (spec F9-4)."""


@dataclass(frozen=True)
class Period:
    """Dates to analyse: ``start`` included, ``end`` excluded; ``None`` means no limit.

    ``Period()`` is the whole mailbox (spec F2-1).
    """

    start: datetime | None = None
    end: datetime | None = None

    def contains(self, moment: datetime) -> bool:
        if self.start is not None and moment < self.start:
            return False
        if self.end is not None and moment >= self.end:
            return False
        return True


@dataclass(frozen=True)
class Folders:
    """Extra folders to analyse besides the normal ones; both off by default (spec F2-3)."""

    include_spam: bool = False
    include_trash: bool = False


@runtime_checkable
class MailProvider(Protocol):
    """Read-only access to one email account."""

    def authorize(self) -> None:
        """Get (or refresh) the user's permission to read the mailbox."""
        ...

    def account_email(self) -> str:
        """Address of the authorised account."""
        ...

    def list_message_ids(self, period: Period, folders: Folders) -> list[str]:
        """IDs of every message in ``period`` and ``folders`` (the exact total for F2-4)."""
        ...

    def get_headers(self, message_id: str) -> Mapping[str, str]:
        """``From``, ``Subject``, ``Date``, ``List-Unsubscribe`` and ``List-Unsubscribe-Post``."""
        ...

    def get_body(self, message_id: str) -> str:
        """HTML body of the message (empty if it has none)."""
        ...

    def revoke(self) -> None:
        """Withdraw the app's permission; may raise ``RevokeNotSupported``."""
        ...
