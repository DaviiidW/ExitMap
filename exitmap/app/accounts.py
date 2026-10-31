"""Connect email accounts (spec F1, F10-1, F10-2).

- Each provider needs the user's own app registration (spec §2, F1-2). It is kept in the
  credential store, one per provider, and only after an authorization has worked with it.
- Connecting authorizes in the browser, reads the account address and keeps the tokens in
  the credential store chosen by the policy (plan §7). An account already connected is not
  added again (F1-7); its tokens are replaced, which is how it gets reconnected.
- Nothing here depends on a concrete provider: providers are built by a factory
  (constitution 1).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from exitmap.domain.models import Account, Provider
from exitmap.errors import InvalidRegistrationError, RegistrationMissingError
from exitmap.providers.base import MailProvider
from exitmap.providers.gmail import GmailProvider
from exitmap.providers.oauth import Tokens
from exitmap.providers.outlook import OutlookProvider
from exitmap.storage.credentials import CredentialStore
from exitmap.storage.db import Database


@dataclass(frozen=True)
class Registration:
    """The user's app registration: ``client_secret`` only for Google (plan §4)."""

    client_id: str
    client_secret: str | None = None


@runtime_checkable
class TokenHolder(Protocol):
    """A provider that can hand over its tokens after authorizing."""

    @property
    def tokens(self) -> Tokens | None: ...


ProviderFactory = Callable[[Provider, Registration, Tokens | None], MailProvider]


def build_provider(
    provider: Provider, registration: Registration, tokens: Tokens | None = None
) -> MailProvider:
    """Real provider for ``provider`` (Gmail API or Microsoft Graph)."""
    if provider is Provider.GMAIL:
        return GmailProvider(registration.client_id, registration.client_secret or "", tokens)
    return OutlookProvider(registration.client_id, tokens)


def clean_registration(provider: Provider, registration: Registration) -> Registration:
    """Registration without surrounding spaces; missing fields → ``InvalidRegistrationError``.

    Google desktop clients need the client secret; Microsoft public clients have none.
    """
    client_id = registration.client_id.strip()
    secret = (registration.client_secret or "").strip() or None
    if not client_id or (provider is Provider.GMAIL and secret is None):
        raise InvalidRegistrationError()
    return Registration(client_id, secret if provider is Provider.GMAIL else None)


def registration_key(provider: Provider) -> str:
    return f"registration:{provider.value}"


def tokens_key(provider: Provider, email: str) -> str:
    return f"tokens:{provider.value}:{email}"


def dump_registration(registration: Registration) -> str:
    return json.dumps(
        {"client_id": registration.client_id, "client_secret": registration.client_secret}
    )


def load_registration(value: str) -> Registration:
    data = json.loads(value)
    return Registration(data["client_id"], data.get("client_secret"))


def dump_tokens(tokens: Tokens) -> str:
    expires_at = tokens.expires_at.isoformat() if tokens.expires_at else None
    return json.dumps(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": expires_at,
            "id_token": tokens.id_token,
        }
    )


def load_tokens(value: str) -> Tokens:
    data = json.loads(value)
    expires_at = data.get("expires_at")
    return Tokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
        id_token=data.get("id_token"),
    )


@dataclass(frozen=True)
class ConnectResult:
    """The connected account; ``already_connected`` means it was not added again (F1-7)."""

    account: Account
    already_connected: bool = False


class AccountService:
    """Connected accounts and their credentials.

    ``store`` is ``None`` while the user still has to choose between a master password and
    session mode (F10-2); the interface sets it before connecting the first account.
    """

    def __init__(
        self,
        db: Database,
        store: CredentialStore | None,
        factory: ProviderFactory = build_provider,
    ) -> None:
        self.db = db
        self.store = store
        self._factory = factory

    def list_accounts(self) -> list[Account]:
        return self.db.list_accounts()

    def _store(self) -> CredentialStore:
        if self.store is None:
            raise RuntimeError("Choose a credential store before connecting accounts")
        return self.store

    def registration(self, provider: Provider) -> Registration | None:
        """Saved registration of ``provider``, if any."""
        value = self._store().get(registration_key(provider))
        return load_registration(value) if value is not None else None

    def needs_registration(self, provider: Provider) -> bool:
        """Whether the user has to enter the registration data first (F1-2)."""
        return self.registration(provider) is None

    def connect(
        self, provider: Provider, registration: Registration | None = None
    ) -> ConnectResult:
        """Authorize an account of ``provider`` and keep it (F1-2, F1-3, F1-5..7, F10-1).

        ``registration`` replaces the saved one; without it the saved one is used, and if
        there is none → ``RegistrationMissingError``. Errors of the authorization
        (cancelled, denied, wrong registration…) reach the caller and nothing is saved.
        """
        store = self._store()
        if registration is None:
            registration = self.registration(provider)
            if registration is None:
                raise RegistrationMissingError()
        registration = clean_registration(provider, registration)

        mail = self._factory(provider, registration, None)
        mail.authorize()
        email = mail.account_email()
        tokens = mail.tokens if isinstance(mail, TokenHolder) else None

        store.set(registration_key(provider), dump_registration(registration))
        if tokens is not None:
            store.set(tokens_key(provider, email), dump_tokens(tokens))

        existing = self._find(provider, email)
        if existing is not None:
            return ConnectResult(existing, already_connected=True)
        account = self.db.add_account(
            Account(provider, email, client_registration_ref=registration_key(provider))
        )
        return ConnectResult(account)

    def _find(self, provider: Provider, email: str) -> Account | None:
        return next(
            (a for a in self.db.list_accounts() if a.provider is provider and a.email == email),
            None,
        )
