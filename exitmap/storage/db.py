"""SQLite schema and repository for accounts, services, evidence and settings (plan §3)."""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from exitmap.domain.models import (
    Account,
    Evidence,
    LinkSource,
    Provider,
    RelationType,
    Service,
    State,
    UnsubscribeMethod,
)
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


def _enum_value(value: StrEnum | None) -> str | None:
    return value.value if value is not None else None


_SERVICE_COLUMNS = (
    "account_id",
    "domain",
    "name",
    "is_registered",
    "is_subscription",
    "is_access",
    "first_email_at",
    "last_email_at",
    "email_count",
    "state",
    "state_changed_at",
    "has_alert",
    "manage_url",
    "manage_url_source",
    "unsubscribe_method",
    "unsubscribe_target",
)


def _service_from_row(row: sqlite3.Row) -> Service:
    relation_types = {
        relation
        for relation, column in (
            (RelationType.REGISTERED, "is_registered"),
            (RelationType.SUBSCRIPTION, "is_subscription"),
            (RelationType.ACCESS, "is_access"),
        )
        if row[column]
    }
    return Service(
        account_id=row["account_id"],
        domain=row["domain"],
        name=row["name"],
        relation_types=relation_types,
        first_email_at=_from_text(row["first_email_at"]),
        last_email_at=_from_text(row["last_email_at"]),
        email_count=row["email_count"],
        state=State(row["state"]),
        state_changed_at=_from_text(row["state_changed_at"]),
        has_alert=bool(row["has_alert"]),
        manage_url=row["manage_url"],
        manage_url_source=_optional(LinkSource, row["manage_url_source"]),
        unsubscribe_method=_optional(UnsubscribeMethod, row["unsubscribe_method"]),
        unsubscribe_target=row["unsubscribe_target"],
        id=row["id"],
    )


def _optional(enum: type[StrEnum], value: str | None) -> StrEnum | None:
    return enum(value) if value is not None else None


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

    def save_service(self, service: Service) -> Service:
        """Insert a new service (``id`` is None) or update an existing one."""
        values = (
            service.account_id,
            service.domain,
            service.name,
            int(RelationType.REGISTERED in service.relation_types),
            int(RelationType.SUBSCRIPTION in service.relation_types),
            int(RelationType.ACCESS in service.relation_types),
            _to_text(service.first_email_at),
            _to_text(service.last_email_at),
            service.email_count,
            service.state.value,
            _to_text(service.state_changed_at),
            int(service.has_alert),
            service.manage_url,
            _enum_value(service.manage_url_source),
            _enum_value(service.unsubscribe_method),
            service.unsubscribe_target,
        )
        with self.conn:
            if service.id is None:
                cursor = self.conn.execute(
                    f"INSERT INTO services ({', '.join(_SERVICE_COLUMNS)})"
                    f" VALUES ({', '.join('?' * len(_SERVICE_COLUMNS))})",
                    values,
                )
                service.id = cursor.lastrowid
            else:
                self.conn.execute(
                    f"UPDATE services SET {', '.join(f'{c} = ?' for c in _SERVICE_COLUMNS)}"
                    " WHERE id = ?",
                    (*values, service.id),
                )
        return service

    def get_service(self, service_id: int) -> Service | None:
        row = self.conn.execute("SELECT * FROM services WHERE id = ?", (service_id,)).fetchone()
        return _service_from_row(row) if row is not None else None

    def list_services(self, account_id: int | None = None) -> list[Service]:
        """List the services of one account, or of all accounts if ``account_id`` is None."""
        if account_id is None:
            rows = self.conn.execute("SELECT * FROM services ORDER BY id")
        else:
            rows = self.conn.execute(
                "SELECT * FROM services WHERE account_id = ? ORDER BY id", (account_id,)
            )
        return [_service_from_row(row) for row in rows]

    def set_state(
        self, service_id: int, state: State, changed_at: datetime | None = None
    ) -> None:
        """Change a service's state and record when it changed (spec F7-2, F8-4)."""
        changed_at = changed_at or datetime.now(timezone.utc)
        with self.conn:
            self.conn.execute(
                "UPDATE services SET state = ?, state_changed_at = ? WHERE id = ?",
                (state.value, _to_text(changed_at), service_id),
            )

    def set_alert(self, service_id: int) -> None:
        """Highlight a service with an alert (spec F8-4)."""
        self._set_has_alert(service_id, True)

    def clear_alert(self, service_id: int) -> None:
        """Remove a service's alert (spec F8-5)."""
        self._set_has_alert(service_id, False)

    def _set_has_alert(self, service_id: int, value: bool) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE services SET has_alert = ? WHERE id = ?", (int(value), service_id)
            )

    def add_evidence(self, evidence: Evidence) -> Evidence:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO evidence (service_id, provider_message_id, subject, sent_at,"
                " relation_type) VALUES (?, ?, ?, ?, ?)",
                (
                    evidence.service_id,
                    evidence.provider_message_id,
                    evidence.subject,
                    _to_text(evidence.sent_at),
                    evidence.relation_type.value,
                ),
            )
        evidence.id = cursor.lastrowid
        return evidence

    def list_evidence(self, service_id: int) -> list[Evidence]:
        rows = self.conn.execute(
            "SELECT * FROM evidence WHERE service_id = ? ORDER BY sent_at, id", (service_id,)
        )
        return [
            Evidence(
                provider_message_id=row["provider_message_id"],
                subject=row["subject"],
                sent_at=_from_text(row["sent_at"]),
                relation_type=RelationType(row["relation_type"]),
                service_id=row["service_id"],
                id=row["id"],
            )
            for row in rows
        ]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
