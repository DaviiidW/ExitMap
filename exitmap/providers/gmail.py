"""Gmail REST API provider (plan §4 "Gmail"; spec F2-1, F2-3).

Everything that is specific to Google lives here (constitution 1).

The analysis covers the whole mailbox (archived mail included) except Sent and Drafts;
Spam and Trash only when the user chooses them (plan §4).
"""

from dataclasses import dataclass

from exitmap.providers.base import Folders, Period
from exitmap.providers.http import HttpClient
from exitmap.providers.oauth import OAuthConfig, OAuthSession, Tokens

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
PAGE_SIZE = 500  # Largest page ``users.messages.list`` allows.


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


class GmailProvider:
    """``MailProvider`` for one Gmail account."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tokens: Tokens | None = None,
        http: HttpClient | None = None,
        endpoints: GoogleEndpoints = GoogleEndpoints(),
    ) -> None:
        self.endpoints = endpoints
        self.session = OAuthSession(
            http or HttpClient(), gmail_config(client_id, client_secret, endpoints), tokens
        )

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
