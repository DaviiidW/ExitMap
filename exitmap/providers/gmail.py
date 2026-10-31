"""Gmail REST API provider (plan §4 "Gmail"; spec F1-4, F2-1, F2-3, F9-3).

Everything that is specific to Google lives here (constitution 1).

- The only scope is ``gmail.readonly``: read-only access (constitution 7, spec F1-4).
- The analysis covers the whole mailbox (archived mail included) except Sent and Drafts;
  Spam and Trash only when the user chooses them (plan §4).
- Headers come from ``format=metadata``; the body (``format=full``) only when asked for.
"""

import base64
import binascii
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import Message
from typing import Any

from exitmap.errors import PermissionExpiredError
from exitmap.providers.base import Folders, Period
from exitmap.providers.http import HttpClient
from exitmap.providers.oauth import OAuthConfig, OAuthSession, Tokens

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
PAGE_SIZE = 500  # Largest page ``users.messages.list`` allows.
METADATA_HEADERS = ("From", "Subject", "Date", "List-Unsubscribe", "List-Unsubscribe-Post")


@dataclass(frozen=True)
class GoogleEndpoints:
    """Google URLs; tests point them to a local server."""

    api: str = "https://gmail.googleapis.com/gmail/v1/users/me"
    auth: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token: str = "https://oauth2.googleapis.com/token"
    revoke: str = "https://oauth2.googleapis.com/revoke"


def gmail_config(
    client_id: str, client_secret: str, endpoints: GoogleEndpoints = GoogleEndpoints()
) -> OAuthConfig:
    return OAuthConfig(
        auth_endpoint=endpoints.auth,
        token_endpoint=endpoints.token,
        client_id=client_id,
        client_secret=client_secret,
        scopes=(READONLY_SCOPE,),
        # ``offline`` returns a refresh token; ``consent`` returns it again on reconnect.
        extra_auth_params={"access_type": "offline", "prompt": "consent"},
    )


def include_spam_trash(folders: Folders) -> bool:
    return folders.include_spam or folders.include_trash


def search_query(period: Period, folders: Folders) -> str:
    """``q`` for ``users.messages.list``: dates as Unix seconds and excluded folders."""
    terms = []
    if period.start is not None:
        terms.append(f"after:{int(period.start.timestamp())}")
    if period.end is not None:
        terms.append(f"before:{int(period.end.timestamp())}")
    terms += ["-in:sent", "-in:drafts"]
    # With ``includeSpamTrash`` both come in: drop the one the user did not choose.
    if include_spam_trash(folders):
        if not folders.include_spam:
            terms.append("-in:spam")
        if not folders.include_trash:
            terms.append("-in:trash")
    return " ".join(terms)


def message_headers(message: Mapping[str, Any]) -> dict[str, str]:
    """The wanted headers of a ``messages.get`` answer, with their usual names."""
    wanted = {name.lower(): name for name in METADATA_HEADERS}
    headers: dict[str, str] = {}
    for header in message.get("payload", {}).get("headers", []):
        name = wanted.get(str(header.get("name", "")).lower())
        if name is not None and name not in headers:
            headers[name] = str(header.get("value", ""))
    return headers


def _charset(part: Mapping[str, Any]) -> str:
    content_type = next(
        (h.get("value", "") for h in part.get("headers", [])
         if str(h.get("name", "")).lower() == "content-type"),
        "",
    )
    parsed = Message()
    parsed["Content-Type"] = content_type
    return parsed.get_content_charset() or "utf-8"


def _decode_part(part: Mapping[str, Any]) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        return raw.decode(_charset(part), errors="replace")
    except (binascii.Error, ValueError, LookupError):
        return ""


def html_body(message: Mapping[str, Any]) -> str:
    """First ``text/html`` part of a ``format=full`` answer, or ``""`` if there is none."""
    pending = [message.get("payload", {})]
    while pending:
        part = pending.pop(0)
        if part.get("mimeType") == "text/html":
            body = _decode_part(part)
            if body:
                return body
        pending[0:0] = part.get("parts", [])
    return ""


class GmailProvider:
    """``MailProvider`` for one Gmail account."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tokens: Tokens | None = None,
        http: HttpClient | None = None,
        endpoints: GoogleEndpoints = GoogleEndpoints(),
        open_browser: Callable[[str], object] = webbrowser.open,
    ) -> None:
        self.endpoints = endpoints
        self._open_browser = open_browser
        self.session = OAuthSession(
            http or HttpClient(), gmail_config(client_id, client_secret, endpoints), tokens
        )

    @property
    def tokens(self) -> Tokens | None:
        """Current tokens, so the app can keep them in the credential store (spec F10)."""
        return self.session.tokens

    def authorize(self) -> None:
        """Ask the user for read-only access in the system browser (spec F1-4, F1-6)."""
        self.session.authorize(self._open_browser)

    def account_email(self) -> str:
        """Address of the account, from ``users.getProfile`` (spec F1-3)."""
        return str(self.session.get_json(f"{self.endpoints.api}/profile")["emailAddress"])

    def list_message_ids(self, period: Period, folders: Folders) -> list[str]:
        """Every ID, page by page, so the total is exact (spec F2-4)."""
        params: dict[str, str | int] = {
            "q": search_query(period, folders),
            "includeSpamTrash": "true" if include_spam_trash(folders) else "false",
            "maxResults": PAGE_SIZE,
        }
        ids: list[str] = []
        while True:
            data = self.session.get_json(f"{self.endpoints.api}/messages", params)
            ids += [message["id"] for message in data.get("messages", [])]
            page_token = data.get("nextPageToken")
            if not page_token:
                return ids
            params["pageToken"] = page_token

    def get_headers(self, message_id: str) -> Mapping[str, str]:
        data = self.session.get_json(
            f"{self.endpoints.api}/messages/{message_id}",
            {"format": "metadata", "metadataHeaders": METADATA_HEADERS},
        )
        return message_headers(data)

    def get_body(self, message_id: str) -> str:
        data = self.session.get_json(
            f"{self.endpoints.api}/messages/{message_id}", {"format": "full"}
        )
        return html_body(data)

    def revoke(self) -> None:
        """Withdraw the app's permission in Google (spec F9-3).

        Revoking the refresh token withdraws the whole grant. Without network →
        ``OfflineError``; without tokens (for example in session mode after reopening the
        app) → ``PermissionExpiredError``. In both cases the app tells the user to do it by
        hand (F9-4).
        """
        tokens = self.session.tokens
        if tokens is None:
            raise PermissionExpiredError()
        token = tokens.refresh_token or tokens.access_token
        self.session.http.post_json(self.endpoints.revoke, form={"token": token})
        self.session.tokens = None
