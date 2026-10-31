"""Microsoft Graph provider for Outlook/Hotmail accounts (plan §4 "Microsoft"; spec F2-1, F2-3).

Everything that is specific to Microsoft lives here (constitution 1).

The analysis covers every folder (archived mail included) except Sent Items and Drafts;
Junk Email and Deleted Items only when the user chooses them (plan §4). Graph lists all
folders at ``/me/messages``; the excluded ones are dropped by ``parentFolderId``.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from exitmap.providers.base import Folders, Period
from exitmap.providers.http import HttpClient
from exitmap.providers.oauth import OAuthConfig, OAuthSession, Tokens

SCOPES = ("Mail.Read", "offline_access", "openid", "email")
# Microsoft compares the redirect host with the registered ``http://localhost`` (plan §4).
REDIRECT_HOST = "localhost"
PAGE_SIZE = 100

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


class OutlookProvider:
    """``MailProvider`` for one Outlook/Hotmail account."""

    def __init__(
        self,
        client_id: str,
        tokens: Tokens | None = None,
        http: HttpClient | None = None,
        endpoints: MicrosoftEndpoints = MicrosoftEndpoints(),
    ) -> None:
        self.endpoints = endpoints
        self.session = OAuthSession(
            http or HttpClient(), outlook_config(client_id, endpoints), tokens
        )

    def _folder_id(self, name: str) -> str:
        return str(self.session.get_json(f"{self.endpoints.api}/mailFolders/{name}")["id"])

    def list_message_ids(self, period: Period, folders: Folders) -> list[str]:
        """Every ID, page by page, so the total is exact (spec F2-4)."""
        excluded = {self._folder_id(name) for name in excluded_folders(folders)}
        params: dict[str, str | int] = {"$select": "id,parentFolderId", "$top": PAGE_SIZE}
        condition = date_filter(period)
        if condition is not None:
            params["$filter"] = condition
        url: str | None = f"{self.endpoints.api}/messages"
        ids: list[str] = []
        while url is not None:
            data = self.session.get_json(url, params)
            ids += [
                message["id"]
                for message in data.get("value", [])
                if message.get("parentFolderId") not in excluded
            ]
            # The next link already carries every parameter.
            url, params = data.get("@odata.nextLink"), {}
        return ids
