"""Microsoft Graph provider for Outlook/Hotmail accounts
(plan §4 "Microsoft"; spec F1-4, F2-1, F2-3, F9-4).

Everything that is specific to Microsoft lives here (constitution 1).

- Scopes: ``Mail.Read offline_access openid email``: read-only mail access, a refresh
  token and the address in the ``id_token`` (constitution 7, spec F1-4).
- The analysis covers every folder (archived mail included) except Sent Items and Drafts;
  Junk Email and Deleted Items only when the user chooses them (plan §4). Graph lists all
  folders at ``/me/messages``; the excluded ones are dropped by ``parentFolderId``.
- The listing also asks for ``internetMessageHeaders``; if Graph does not return them for a
  message, they are asked for that message alone (plan §8).
- Microsoft does not let the app withdraw its own permission → ``RevokeNotSupported``.
"""

import base64
import binascii
import json
import webbrowser
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from exitmap.errors import ExitMapError
from exitmap.providers.base import Folders, Period, RevokeNotSupported
from exitmap.providers.http import HttpClient
from exitmap.providers.oauth import OAuthConfig, OAuthSession, Tokens

SCOPES = ("Mail.Read", "offline_access", "openid", "email")
# Microsoft compares the redirect host with the registered ``http://localhost`` (plan §4).
REDIRECT_HOST = "localhost"
PAGE_SIZE = 100

HEADER_NAMES = ("From", "Subject", "Date", "List-Unsubscribe", "List-Unsubscribe-Post")
LIST_FIELDS = "id,parentFolderId,internetMessageHeaders"

ALWAYS_EXCLUDED = ("sentitems", "drafts")
SPAM_FOLDER = "junkemail"
TRASH_FOLDER = "deleteditems"


@dataclass(frozen=True)
class MicrosoftEndpoints:
    """Microsoft URLs (``common`` authority); tests point them to a local server."""

    api: str = "https://graph.microsoft.com/v1.0/me"
    auth: str = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    token: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def outlook_config(
    client_id: str, endpoints: MicrosoftEndpoints = MicrosoftEndpoints()
) -> OAuthConfig:
    """Public client: no secret (plan §4)."""
    return OAuthConfig(
        auth_endpoint=endpoints.auth,
        token_endpoint=endpoints.token,
        client_id=client_id,
        scopes=SCOPES,
        redirect_host=REDIRECT_HOST,
    )


def excluded_folders(folders: Folders) -> list[str]:
    """Well-known names of the folders whose messages are not analysed."""
    names = list(ALWAYS_EXCLUDED)
    if not folders.include_spam:
        names.append(SPAM_FOLDER)
    if not folders.include_trash:
        names.append(TRASH_FOLDER)
    return names


def _graph_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def date_filter(period: Period) -> str | None:
    """``$filter`` on ``receivedDateTime``: start included, end excluded."""
    terms = []
    if period.start is not None:
        terms.append(f"receivedDateTime ge {_graph_time(period.start)}")
    if period.end is not None:
        terms.append(f"receivedDateTime lt {_graph_time(period.end)}")
    return " and ".join(terms) or None


def wanted_headers(items: Iterable[Mapping[str, Any]] | None) -> dict[str, str]:
    """The wanted ``internetMessageHeaders``, with their usual names."""
    wanted = {name.lower(): name for name in HEADER_NAMES}
    headers: dict[str, str] = {}
    for item in items or []:
        name = wanted.get(str(item.get("name", "")).lower())
        if name is not None and name not in headers:
            headers[name] = str(item.get("value", ""))
    return headers


def email_from_id_token(id_token: str | None) -> str:
    """Address in the ``id_token`` (``email`` claim, else ``preferred_username``).

    The token comes straight from Microsoft's token endpoint over TLS, so its signature is
    not checked (OpenID Connect Core §3.1.3.7).
    """
    try:
        payload = id_token.split(".")[1]  # type: ignore[union-attr]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        email = claims.get("email") or claims.get("preferred_username")
    except (AttributeError, IndexError, binascii.Error, ValueError):
        email = None
    if not isinstance(email, str) or "@" not in email:
        raise ExitMapError()
    return email


class OutlookProvider:
    """``MailProvider`` for one Outlook/Hotmail account."""

    def __init__(
        self,
        client_id: str,
        tokens: Tokens | None = None,
        http: HttpClient | None = None,
        endpoints: MicrosoftEndpoints = MicrosoftEndpoints(),
        open_browser: Callable[[str], object] = webbrowser.open,
    ) -> None:
        self.endpoints = endpoints
        self._open_browser = open_browser
        self._headers: dict[str, dict[str, str]] = {}
        self.session = OAuthSession(
            http or HttpClient(), outlook_config(client_id, endpoints), tokens
        )

    @property
    def tokens(self) -> Tokens | None:
        """Current tokens, so the app can keep them in the credential store (spec F10)."""
        return self.session.tokens

    def authorize(self) -> None:
        """Ask the user for read-only access in the system browser (spec F1-4, F1-6)."""
        self.session.authorize(self._open_browser)

    def account_email(self) -> str:
        """Address of the account, from the ``id_token`` (spec F1-3)."""
        tokens = self.session.tokens
        return email_from_id_token(tokens.id_token if tokens else None)

    def _folder_id(self, name: str) -> str:
        return str(self.session.get_json(f"{self.endpoints.api}/mailFolders/{name}")["id"])

    def list_message_ids(self, period: Period, folders: Folders) -> list[str]:
        """Every ID, page by page, so the total is exact (spec F2-4)."""
        excluded = {self._folder_id(name) for name in excluded_folders(folders)}
        params: dict[str, str | int] = {"$select": LIST_FIELDS, "$top": PAGE_SIZE}
        condition = date_filter(period)
        if condition is not None:
            params["$filter"] = condition
        url: str | None = f"{self.endpoints.api}/messages"
        ids: list[str] = []
        self._headers = {}
        while url is not None:
            data = self.session.get_json(url, params)
            for message in data.get("value", []):
                if message.get("parentFolderId") in excluded:
                    continue
                ids.append(message["id"])
                if message.get("internetMessageHeaders"):
                    self._headers[message["id"]] = wanted_headers(
                        message["internetMessageHeaders"]
                    )
            # The next link already carries every parameter.
            url, params = data.get("@odata.nextLink"), {}
        return ids

    def get_headers(self, message_id: str) -> Mapping[str, str]:
        cached = self._headers.pop(message_id, None)
        if cached is not None:
            return cached
        data = self.session.get_json(
            f"{self.endpoints.api}/messages/{message_id}", {"$select": "internetMessageHeaders"}
        )
        return wanted_headers(data.get("internetMessageHeaders"))

    def get_body(self, message_id: str) -> str:
        data = self.session.get_json(
            f"{self.endpoints.api}/messages/{message_id}", {"$select": "body"}
        )
        body = data.get("body") or {}
        return str(body.get("content") or "") if body.get("contentType") == "html" else ""

    def revoke(self) -> None:
        """Microsoft has no endpoint for this with personal accounts (plan §4, spec F9-4)."""
        raise RevokeNotSupported()
