"""Connect and remove email accounts (spec F1, F9, F10-1, F10-2).

- Each provider needs the user's own app registration (spec §2, F1-2). It is kept in the
  credential store, one per provider, and only after an authorization has worked with it.
- Connecting authorizes in the browser, reads the account address and keeps the tokens in
  the credential store chosen by the policy (plan §7). An account already connected is not
  added again (F1-7); its tokens are replaced, which is how it gets reconnected.
- Removing an account withdraws the app's permission when the provider allows it (Gmail)
  and then deletes its credentials and, by cascade, its services, evidence and states. If
  the permission cannot be withdrawn (Outlook, no network…) the local data is deleted
  anyway and the result says where to do it by hand (F9-4).
- Nothing here depends on a concrete provider: providers are built by a factory
  (constitution 1).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from exitmap.domain.models import Account, Provider
from exitmap.errors import ExitMapError, InvalidRegistrationError, RegistrationMissingError
from exitmap.providers.base import MailProvider, RevokeNotSupported
from exitmap.providers.gmail import PERMISSIONS_URL as GOOGLE_PERMISSIONS_URL
from exitmap.providers.gmail import GmailProvider
from exitmap.providers.oauth import Tokens
from exitmap.providers.outlook import PERMISSIONS_URL as MICROSOFT_PERMISSIONS_URL
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


PERMISSIONS_URLS = {
    Provider.GMAIL: GOOGLE_PERMISSIONS_URL,
    Provider.OUTLOOK: MICROSOFT_PERMISSIONS_URL,
}


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


@dataclass(frozen=True)
class RemovalSummary:
    """What removing an account deletes (F9-1): its credentials and its services with
    their evidence and states."""

    account: Account
    service_count: int


@dataclass(frozen=True)
class RemovalResult:
    """``manual_revoke_url`` is set when the user must withdraw the permission by hand."""

    revoked: bool
    manual_revoke_url: str | None = None


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

    def with_db(self, db: Database) -> "AccountService":
        """The same store and factory on another connection.

        SQLite connections are bound to their thread, so the interface connects accounts
        in a background thread with its own connection (the authorization waits for the
        browser).
        """
        return AccountService(db, self.store, self._factory)

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

    def removal_summary(self, account_id: int) -> RemovalSummary:
        """Data for the confirmation shown before removing an account (F9-1)."""
        account = self._account(account_id)
        return RemovalSummary(account, len(self.db.list_services(account_id)))

    def remove(self, account_id: int) -> RemovalResult:
        """Remove a confirmed account (F9-2..4).

        The permission is withdrawn first, while the tokens still exist. Credentials are
        deleted before the account, so a failing keyring leaves the account in the list
        and the user can try again.
        """
        account = self._account(account_id)
        store = self._store()
        revoked = self._revoke(account, store)
        store.delete(tokens_key(account.provider, account.email))
        self.db.delete_account(account_id)
        if revoked:
            return RemovalResult(revoked=True)
        return RemovalResult(revoked=False, manual_revoke_url=PERMISSIONS_URLS[account.provider])

    def _revoke(self, account: Account, store: CredentialStore) -> bool:
        registration = self.registration(account.provider)
        if registration is None:
            return False
        value = store.get(tokens_key(account.provider, account.email))
        tokens = load_tokens(value) if value is not None else None
        try:
            self._factory(account.provider, registration, tokens).revoke()
        except (RevokeNotSupported, ExitMapError):
            return False
        return True

    def _account(self, account_id: int) -> Account:
        account = next((a for a in self.db.list_accounts() if a.id == account_id), None)
        if account is None:
            raise ExitMapError()
        return account

    def _find(self, provider: Provider, email: str) -> Account | None:
        return next(
            (a for a in self.db.list_accounts() if a.provider is provider and a.email == email),
            None,
        )
