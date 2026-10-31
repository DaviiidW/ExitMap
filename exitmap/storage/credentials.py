"""Credential stores for OAuth tokens and registration data (plan §7, spec F10).

Every store keeps opaque text values under a text key; callers decide what the key and
value mean (for example, one key per connected account).
"""

import base64
import hashlib
import json
import os
import secrets
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

import keyring
from cryptography.fernet import Fernet, InvalidToken
from keyring.backend import KeyringBackend
from keyring.backends import fail, null
from keyring.errors import KeyringError, PasswordDeleteError

from exitmap.errors import KeyringUnavailableError, WrongPasswordError
from exitmap.storage.db import Database

KEYRING_SERVICE = "ExitMap"
CREDENTIALS_FILE_NAME = "credentials.enc"
CREDENTIALS_FILE_MODE = 0o600

SESSION_MODE_KEY = "session_mode"

SALT_BYTES = 16
# scrypt cost (n=2^15, r=8, p=1) as recommended for interactive logins; needs 32 MiB.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024


@runtime_checkable
class CredentialStore(Protocol):
    """Where credentials are kept."""

    def get(self, key: str) -> str | None:
        """Stored value for ``key``, or ``None`` if there is none."""
        ...

    def set(self, key: str, value: str) -> None:
        """Store ``value`` under ``key``, replacing any previous value."""
        ...

    def delete(self, key: str) -> None:
        """Remove ``key``; does nothing if it is not stored."""
        ...


class MemoryStore:
    """Session mode: credentials live only in memory and are lost on close (spec F10-6)."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)


def keyring_available(backend: KeyringBackend | None = None) -> bool:
    """Whether the system has a usable keyring (spec F10-1, F10-2).

    ``keyring`` falls back to its ``fail`` backend when no keyring is found, and to the
    ``null`` backend when it has been disabled.
    """
    backend = keyring.get_keyring() if backend is None else backend
    return not isinstance(backend, (fail.Keyring, null.Keyring))


class KeyringStore:
    """System keyring: Credential Manager on Windows, Secret Service/KWallet on Linux."""

    def __init__(self, backend: KeyringBackend | None = None) -> None:
        self._backend = keyring.get_keyring() if backend is None else backend

    def get(self, key: str) -> str | None:
        try:
            return self._backend.get_password(KEYRING_SERVICE, key)
        except KeyringError as exc:
            raise KeyringUnavailableError() from exc

    def set(self, key: str, value: str) -> None:
        try:
            self._backend.set_password(KEYRING_SERVICE, key, value)
        except KeyringError as exc:
            raise KeyringUnavailableError() from exc

    def delete(self, key: str) -> None:
        try:
            self._backend.delete_password(KEYRING_SERVICE, key)
        except PasswordDeleteError:
            pass
        except KeyringError as exc:
            raise KeyringUnavailableError() from exc


def _derive_key(password: str, salt: bytes) -> bytes:
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=32,
    )
    return base64.urlsafe_b64encode(key)


class EncryptedFileStore:
    """Credentials in a file encrypted with the master password (spec F10-2..5).

    The key comes from the password with scrypt and a random salt; the values are
    encrypted with Fernet. The whole file is rewritten on every change.
    """

    def __init__(
        self,
        path: Path,
        fernet: Fernet,
        salt: bytes,
        values: dict[str, str],
        platform: str | None = None,
    ) -> None:
        self.path = Path(path)
        self._fernet = fernet
        self._salt = salt
        self._values = values
        self._platform = sys.platform if platform is None else platform

    @classmethod
    def create(cls, path: Path, password: str, platform: str | None = None) -> "EncryptedFileStore":
        """Start an empty store protected by a new ``password``, replacing any old file."""
        salt = secrets.token_bytes(SALT_BYTES)
        store = cls(path, Fernet(_derive_key(password, salt)), salt, {}, platform)
        store._save()
        return store

    @classmethod
    def open(cls, path: Path, password: str, platform: str | None = None) -> "EncryptedFileStore":
        """Open an existing store; a wrong password raises ``WrongPasswordError`` (F10-4).

        A damaged file cannot be told apart from a wrong password; in both cases the way
        out is the same: reset (F10-5).
        """
        try:
            content = json.loads(Path(path).read_text(encoding="utf-8"))
            salt = base64.b64decode(content["salt"], validate=True)
            fernet = Fernet(_derive_key(password, salt))
            values = json.loads(fernet.decrypt(content["data"].encode("ascii")))
        except (InvalidToken, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise WrongPasswordError() from exc
        return cls(path, fernet, salt, values, platform)

    @staticmethod
    def exists(path: Path) -> bool:
        return Path(path).exists()

    @staticmethod
    def reset(path: Path) -> None:
        """Forgotten password: delete the encrypted credentials (F10-5).

        Only this file is removed; the database with results and states stays.
        """
        Path(path).unlink(missing_ok=True)

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value
        self._save()

    def delete(self, key: str) -> None:
        if self._values.pop(key, None) is not None:
            self._save()

    def _save(self) -> None:
        data = self._fernet.encrypt(json.dumps(self._values).encode("utf-8"))
        content = json.dumps(
            {"salt": base64.b64encode(self._salt).decode("ascii"), "data": data.decode("ascii")}
        )
        # Write a sibling file and rename it, so a crash never leaves a half-written store.
        tmp = self.path.with_name(self.path.name + ".tmp")
        if not self._platform.startswith("win"):
            tmp.touch(mode=CREDENTIALS_FILE_MODE, exist_ok=True)
            os.chmod(tmp, CREDENTIALS_FILE_MODE)
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, self.path)


def session_mode(db: Database) -> bool:
    """Whether the session mode setting is on (spec F10-6); off by default."""
    return db.get_setting(SESSION_MODE_KEY) == "1"


def set_session_mode(db: Database, enabled: bool) -> None:
    db.set_setting(SESSION_MODE_KEY, "1" if enabled else "0")


class StoreNeed(StrEnum):
    """What the user has to do before a store can be used."""

    NOTHING = "nothing"
    PASSWORD = "password"  # enter the master password (F10-3)
    CHOICE = "choice"  # choose master password or session mode (F10-2)


@dataclass(frozen=True)
class StoreDecision:
    """``store`` is set only when ``need`` is ``NOTHING``."""

    need: StoreNeed
    store: CredentialStore | None = None


def choose_store(
    db: Database, data_dir: Path, backend: KeyringBackend | None = None
) -> StoreDecision:
    """Pick the credential store (plan §7).

    1. Session mode on → memory only, nothing on disk (F10-6, F10-7).
    2. Keyring available → keyring (F10-1).
    3. No keyring → master password if the encrypted file exists (F10-3), otherwise the
       user must choose between a master password and session mode (F10-2).
    """
    if session_mode(db):
        return StoreDecision(StoreNeed.NOTHING, MemoryStore())
    backend = keyring.get_keyring() if backend is None else backend
    if keyring_available(backend):
        return StoreDecision(StoreNeed.NOTHING, KeyringStore(backend))
    if EncryptedFileStore.exists(Path(data_dir) / CREDENTIALS_FILE_NAME):
        return StoreDecision(StoreNeed.PASSWORD)
    return StoreDecision(StoreNeed.CHOICE)


def store_from_choice(db: Database, data_dir: Path, password: str | None) -> CredentialStore:
    """Store after the choice of a user without keyring (F10-2).

    With ``password`` → a new encrypted file protected by it. Without it → session mode,
    which stays on as the setting so the user is not asked again.
    """
    if password is None:
        set_session_mode(db, True)
        return MemoryStore()
    return EncryptedFileStore.create(Path(data_dir) / CREDENTIALS_FILE_NAME, password)
