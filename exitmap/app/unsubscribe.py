"""Unsubscribe from a service's commercial email (spec F5-2..5; plan §4 "Baja").

Called only after the user has confirmed (F5-1, F5-6; constitution 8).

- One-click: ``POST`` to the ``List-Unsubscribe`` link (RFC 8058). A 2xx answer means
  done and the state becomes *unsubscribed* (F5-2). Any failure gives the reason, opens the
  same link in the browser instead and leaves the state as it was (F5-3).
- Web link: opened in the browser; the state does not change (F5-4).
- ``mailto:``: the user's mail program opens with the message ready, never sent by the app;
  the state does not change (F5-5).

Opening the browser and the mail program goes through an injectable ``Opener``.
"""

import os
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from exitmap.domain.models import State, UnsubscribeMethod
from exitmap.errors import ExitMapError, OfflineError, UnsubscribeFailedError
from exitmap.providers.http import HttpClient
from exitmap.storage.db import Database

# RFC 8058 §3.1: the body of the one-click POST.
ONE_CLICK_FORM = {"List-Unsubscribe": "One-Click"}
# Subject of the prepared email when the link brings none.
DEFAULT_MAIL_SUBJECT = "unsubscribe"


class Opener(Protocol):
    """Opens links outside the app."""

    def open_url(self, url: str) -> None:
        """Open a web page in the system browser."""
        ...

    def open_mail(self, uri: str) -> None:
        """Open the user's mail program with a ``mailto:`` message (never sends it)."""
        ...


class SystemOpener:
    """Browser with ``webbrowser``; mail program with ``os.startfile`` on Windows and
    ``xdg-open`` on Linux."""

    def __init__(
        self,
        platform: str | None = None,
        browser: Callable[[str], object] = webbrowser.open,
        run: Callable[[Sequence[str]], object] = subprocess.Popen,
        startfile: Callable[[str], object] | None = None,
    ) -> None:
        self._platform = sys.platform if platform is None else platform
        self._browser = browser
        self._run = run
        self._startfile = startfile if startfile is not None else getattr(os, "startfile", None)

    def open_url(self, url: str) -> None:
        self._browser(url)

    def open_mail(self, uri: str) -> None:
        if self._platform.startswith("win") and self._startfile is not None:
            self._startfile(uri)
        elif self._platform.startswith("linux"):
            self._run(["xdg-open", uri])
        else:
            self._browser(uri)


def prepared_mailto(uri: str) -> str:
    """``mailto:`` URI with a subject, so the message is ready to send (F5-5)."""
    parts = urlsplit(uri)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if any(name.lower() == "subject" and value.strip() for name, value in query):
        return uri
    query = [(n, v) for n, v in query if n.lower() != "subject"]
    query.append(("subject", DEFAULT_MAIL_SUBJECT))
    return urlunsplit(parts._replace(query=urlencode(query)))


class Outcome(StrEnum):
    """What happened after the confirmation."""

    DONE = "done"  # one-click worked, state is now *unsubscribed* (F5-2)
    FAILED_WEB_OPENED = "failed_web_opened"  # one-click failed, web link opened (F5-3)
    WEB_OPENED = "web_opened"  # F5-4
    MAIL_PREPARED = "mail_prepared"  # F5-5


@dataclass(frozen=True)
class UnsubscribeResult:
    """``error`` is the reason of a failed one-click (F5-3); ``opened`` what was opened."""

    outcome: Outcome
    opened: str | None = None
    error: ExitMapError | None = None


class UnsubscribeService:
    """Runs the unsubscribe method of a service."""

    def __init__(
        self,
        db: Database,
        http: HttpClient | None = None,
        opener: Opener | None = None,
    ) -> None:
        self.db = db
        self.http = http or HttpClient()
        self.opener = opener or SystemOpener()

    def unsubscribe(self, service_id: int) -> UnsubscribeResult:
        """Unsubscribe with the method of the service, after the user's confirmation."""
        service = self.db.get_service(service_id)
        if service is None or not service.unsubscribe_method or not service.unsubscribe_target:
            raise ExitMapError()
        target = service.unsubscribe_target
        method = service.unsubscribe_method

        if method is UnsubscribeMethod.ONE_CLICK:
            try:
                self.http.post_form(target, ONE_CLICK_FORM)
            except OfflineError as exc:
                return self._fallback(target, exc)
            except ExitMapError:
                return self._fallback(target, UnsubscribeFailedError())
            self.db.set_state(service_id, State.UNSUBSCRIBED)
            return UnsubscribeResult(Outcome.DONE)

        if method is UnsubscribeMethod.WEB:
            self.opener.open_url(target)
            return UnsubscribeResult(Outcome.WEB_OPENED, opened=target)

        uri = prepared_mailto(target)
        self.opener.open_mail(uri)
        return UnsubscribeResult(Outcome.MAIL_PREPARED, opened=uri)

    def _fallback(self, target: str, error: ExitMapError) -> UnsubscribeResult:
        self.opener.open_url(target)
        return UnsubscribeResult(Outcome.FAILED_WEB_OPENED, opened=target, error=error)
