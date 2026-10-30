"""Credential stores for OAuth tokens and registration data (plan §7, spec F10).

Every store keeps opaque text values under a text key; callers decide what the key and
value mean (for example, one key per connected account).
"""

from typing import Protocol, runtime_checkable

import keyring
from keyring.backend import KeyringBackend
from keyring.backends import fail, null
from keyring.errors import KeyringError, PasswordDeleteError

from exitmap.errors import KeyringUnavailableError

KEYRING_SERVICE = "ExitMap"


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
