"""SQLite schema and account repository (plan §3)."""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from exitmap.domain.models import Account, Provider
from exitmap.errors import AccountAlreadyConnectedError

DB_FILE_MODE = 0o600

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    email TEXT NOT NULL,
    client_registration_ref TEXT,
    last_complete_analysis_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (provider, email)
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    name TEXT NOT NULL,
    is_registered INTEGER NOT NULL DEFAULT 0,
    is_subscription INTEGER NOT NULL DEFAULT 0,
    is_access INTEGER NOT NULL DEFAULT 0,
    first_email_at TEXT,
    last_email_at TEXT,
    email_count INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'pending',
    state_changed_at TEXT,
    has_alert INTEGER NOT NULL DEFAULT 0,
    manage_url TEXT,
    manage_url_source TEXT,
    unsubscribe_method TEXT,
    unsubscribe_target TEXT,
    UNIQUE (account_id, domain)
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    service_id INTEGER NOT NULL REFERENCES services (id) ON DELETE CASCADE,
    provider_message_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    relation_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _from_text(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class Database:
    """Open (and create if needed) the ExitMap database."""

    def __init__(self, path: Path | str, platform: str | None = None) -> None:
        platform = sys.platform if platform is None else platform
        self.path = path
        is_file = str(path) != ":memory:"
        if is_file and not platform.startswith("win"):
            # Create the file owner-only before sqlite opens it (plan §2: 0600 on Linux).
            Path(path).touch(mode=DB_FILE_MODE, exist_ok=True)
            os.chmod(path, DB_FILE_MODE)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self.conn:
            self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def add_account(self, account: Account) -> Account:
        """Insert an account and return it with ``id`` and ``created_at`` set.

        Raises ``AccountAlreadyConnectedError`` if provider+email already exists.
        """
        created_at = account.created_at or datetime.now(timezone.utc)
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "INSERT INTO accounts (provider, email, client_registration_ref,"
                    " last_complete_analysis_at, created_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        account.provider.value,
                        account.email,
                        account.client_registration_ref,
                        _to_text(account.last_complete_analysis_at),
                        _to_text(created_at),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AccountAlreadyConnectedError() from exc
        account.id = cursor.lastrowid
        account.created_at = created_at
        return account

    def list_accounts(self) -> list[Account]:
        rows = self.conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
        return [
            Account(
                provider=Provider(row["provider"]),
                email=row["email"],
                client_registration_ref=row["client_registration_ref"],
                last_complete_analysis_at=_from_text(row["last_complete_analysis_at"]),
                created_at=_from_text(row["created_at"]),
                id=row["id"],
            )
            for row in rows
        ]

    def delete_account(self, account_id: int) -> None:
        """Delete an account and, by cascade, its services and evidence (spec F9-2)."""
        with self.conn:
            self.conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
