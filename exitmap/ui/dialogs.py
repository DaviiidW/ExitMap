"""Dialogs and flows shared by the windows (plan §2 ``ui/dialogs.py``).

- Messages and confirmations go through ``show_error``, ``show_info`` and ``confirm``.
- ``run_in_background`` runs slow work (the authorization waits for the browser) in a
  thread and hands the result back to Tk with ``after()``.
- Connecting an account: provider, registration data with a link to the guide, waiting
  for the browser and the messages of each outcome (spec F1-1, F1-2, F1-6, F1-7).
- Removing an account: confirmation with what is deleted and final message, with where to
  withdraw the permission by hand if needed (spec F9-1, F9-4).
- Credentials: master password or session mode without keyring, unlocking with the
  master password, reset, and the session mode setting (spec F10-2..7).
"""

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import font, messagebox, ttk
from typing import Any

from exitmap.app.accounts import AccountService, ConnectResult, Registration, RemovalResult
from exitmap.app.unsubscribe import Opener
from exitmap.domain.models import Account, Provider
from exitmap.errors import (
    AccountAlreadyConnectedError,
    ExitMapError,
    InvalidRegistrationError,
    RegistrationMissingError,
    WrongPasswordError,
)
from exitmap.storage.credentials import (
    CREDENTIALS_FILE_NAME,
    CredentialStore,
    EncryptedFileStore,
    enable_session_mode,
    session_mode,
    set_session_mode,
    store_from_choice,
)
from exitmap.storage.db import Database
from exitmap.ui import presenters
from exitmap.ui import strings_es as text

# The app runs from the repository, where the registration guide lives (spec §2).
GUIDE_PATH = Path(__file__).resolve().parents[2] / "docs" / "guia-registro.md"

POLL_MS = 100

logger = logging.getLogger(__name__)


def fit_treeview_rows(widget: tk.Misc) -> None:
    """Rows as tall as the font, so they are not clipped on scaled screens."""
    row_height = font.nametofont("TkDefaultFont").metrics("linespace") + 6
    ttk.Style(widget).configure("Treeview", rowheight=row_height)


def show_error(parent: tk.Misc, error: ExitMapError) -> None:
    messagebox.showerror(text.ERROR_TITLE, error.user_message, parent=parent)


def show_info(parent: tk.Misc, message: str) -> None:
    messagebox.showinfo(text.INFO_TITLE, message, parent=parent)


def confirm(parent: tk.Misc, message: str) -> bool:
    """Explicit confirmation; nothing is done unless the user accepts (constitution 8)."""
    return bool(messagebox.askokcancel(text.INFO_TITLE, message, parent=parent))


def user_error(exc: BaseException) -> ExitMapError:
    """Error to show; only the type of an unexpected one is logged (constitution 6)."""
    if isinstance(exc, ExitMapError):
        return exc
    logger.warning("Unexpected error: %s", type(exc).__name__)
    return ExitMapError()


def run_in_background(
    widget: tk.Misc,
    work: Callable[[], Any],
    on_done: Callable[[bool, Any], None],
) -> threading.Thread:
    """Run ``work`` in a thread; ``on_done(ok, result_or_exception)`` runs in Tk's thread."""
    box: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def target() -> None:
        try:
            box.put((True, work()))
        except Exception as exc:  # noqa: BLE001 - every failure must reach the user
            box.put((False, exc))

    def poll() -> None:
        try:
            ok, value = box.get_nowait()
        except queue.Empty:
            widget.after(POLL_MS, poll)
            return
        on_done(ok, value)

    thread = threading.Thread(target=target, name="exitmap-background", daemon=True)
    thread.start()
    widget.after(POLL_MS, poll)
    return thread


class ModalDialog(tk.Toplevel):
    """Dialog on top of its parent; ``show()`` waits until it closes and returns ``result``."""

    def __init__(self, parent: tk.Misc, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result: Any = None
        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def show(self) -> Any:
        self.wait_visibility()
        self.grab_set()
        self.wait_window()
        return self.result

    def close(self, result: Any) -> None:
        self.result = result
        self.destroy()

    def cancel(self) -> None:
        self.close(None)


class ProviderDialog(ModalDialog):
    """Choose Gmail or Outlook (F1-1)."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, text.CHOOSE_PROVIDER_TITLE)
        ttk.Label(self.body, text=text.CHOOSE_PROVIDER).pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(self.body)
        buttons.pack(fill="x")
        self.buttons = {}
        for provider in Provider:
            button = ttk.Button(
                buttons,
                text=text.PROVIDER_LABELS[provider.value],
                command=lambda p=provider: self.close(p),
            )
            button.pack(side="left", padx=(0, 6))
            self.buttons[provider] = button
        ttk.Button(buttons, text=text.CANCEL, command=self.cancel).pack(side="right")


class RegistrationDialog(ModalDialog):
    """Ask for the user's app registration, with a link to the guide (F1-2).

    ``error`` explains what was wrong with the data entered before.
    """

    def __init__(
        self,
        parent: tk.Misc,
        provider: Provider,
        opener: Opener,
        error: str | None = None,
    ) -> None:
        name = text.PROVIDER_LABELS[provider.value]
        super().__init__(parent, text.REGISTRATION_TITLE.format(provider=name))
        self.provider = provider
        self.opener = opener
        ttk.Label(
            self.body, text=text.REGISTRATION_INTRO.format(provider=name), wraplength=420
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        self.guide = ttk.Button(self.body, text=text.GUIDE_LINK, command=self.open_guide)
        self.guide.grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        self.error = ttk.Label(self.body, text=error or "", foreground="#b00020",
                               wraplength=420)
        if error:
            self.error.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.client_id = tk.StringVar()
        self.client_secret = tk.StringVar()
        ttk.Label(self.body, text=text.CLIENT_ID).grid(row=3, column=0, sticky="w")
        ttk.Entry(self.body, textvariable=self.client_id, width=50).grid(row=3, column=1)
        if provider is Provider.GMAIL:
            ttk.Label(self.body, text=text.CLIENT_SECRET).grid(row=4, column=0, sticky="w")
            ttk.Entry(self.body, textvariable=self.client_secret, width=50).grid(
                row=4, column=1, pady=(4, 0)
            )

        buttons = ttk.Frame(self.body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text=text.OK, command=self.accept).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text=text.CANCEL, command=self.cancel).pack(side="left")

    def open_guide(self) -> None:
        self.opener.open_url(GUIDE_PATH.as_uri())

    def accept(self) -> None:
        secret = self.client_secret.get() if self.provider is Provider.GMAIL else None
        self.close(Registration(self.client_id.get(), secret))


class WaitDialog(tk.Toplevel):
    """Message shown while the user authorizes in the browser.

    It cannot be closed: it goes away when the authorization ends, is denied or times out.
    """

    def __init__(self, parent: tk.Misc, message: str) -> None:
        super().__init__(parent)
        self.title(text.INFO_TITLE)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(self, text=message, padding=16, justify="left").pack()


ConnectRunner = Callable[[Provider, Registration | None], ConnectResult]


def background_connect(accounts: AccountService, db_path: Path | str) -> ConnectRunner:
    """Connect with a connection of its own, as it runs in a background thread."""

    def run(provider: Provider, registration: Registration | None) -> ConnectResult:
        with Database(db_path) as db:
            return accounts.with_db(db).connect(provider, registration)

    return run


class ConnectFlow:
    """Connect an account from the interface (F1-1, F1-2, F1-3, F1-5, F1-6, F1-7).

    ``ask_provider`` and ``ask_registration`` open the dialogs; tests replace them.
    """

    def __init__(
        self,
        parent: tk.Misc,
        accounts: AccountService,
        run: ConnectRunner,
        opener: Opener,
        on_connected: Callable[[], None],
        ask_provider: Callable[[], Provider | None] | None = None,
        ask_registration: Callable[[Provider, str | None], Registration | None] | None = None,
        choose_store: Callable[[], CredentialStore | None] | None = None,
        on_network: Callable[[BaseException | None], None] = lambda error: None,
    ) -> None:
        self.parent = parent
        self.choose_store = choose_store
        self.on_network = on_network
        self.accounts = accounts
        self.run = run
        self.opener = opener
        self.on_connected = on_connected
        self.ask_provider = ask_provider or (lambda: ProviderDialog(parent).show())
        self.ask_registration = ask_registration or (
            lambda provider, error: RegistrationDialog(parent, provider, opener, error).show()
        )
        self.waiting: WaitDialog | None = None

    def start(self, provider: Provider | None = None) -> None:
        """Connect an account; with ``provider`` (reconnecting) it is not asked."""
        if self.accounts.store is None:
            # No keyring: choose master password or session mode first (F10-2).
            store = self.choose_store() if self.choose_store is not None else None
            if store is None:
                return
            self.accounts.store = store
        provider = provider or self.ask_provider()
        if provider is None:
            return
        registration = None
        if self.accounts.needs_registration(provider):
            registration = self.ask_registration(provider, None)
            if registration is None:
                return
        self._connect(provider, registration)

    def _connect(self, provider: Provider, registration: Registration | None) -> None:
        self.waiting = WaitDialog(self.parent, text.WAITING_AUTHORIZATION)
        run_in_background(
            self.parent,
            lambda: self.run(provider, registration),
            lambda ok, value: self._done(provider, ok, value),
        )

    def _done(self, provider: Provider, ok: bool, value: Any) -> None:
        if self.waiting is not None:
            self.waiting.destroy()
            self.waiting = None
        self.on_network(None if ok else value)
        if ok:
            self.on_connected()
            if value.already_connected:
                show_info(self.parent, AccountAlreadyConnectedError().user_message)
            return
        if isinstance(value, (InvalidRegistrationError, RegistrationMissingError)):
            registration = self.ask_registration(provider, value.user_message)
            if registration is not None:
                self._connect(provider, registration)
            return
        show_error(self.parent, user_error(value))


RemoveRunner = Callable[[int], RemovalResult]


def background_remove(accounts: AccountService, db_path: Path | str) -> RemoveRunner:
    """Remove with a connection of its own, as it runs in a background thread (the
    permission is withdrawn over the network)."""

    def run(account_id: int) -> RemovalResult:
        with Database(db_path) as db:
            return accounts.with_db(db).remove(account_id)

    return run


class RemoveAccountFlow:
    """Remove an account from the interface after confirming it (F9-1..4)."""

    def __init__(
        self,
        parent: tk.Misc,
        accounts: AccountService,
        run: RemoveRunner,
        on_removed: Callable[[], None],
        on_network: Callable[[BaseException | None], None] = lambda error: None,
    ) -> None:
        self.parent = parent
        self.accounts = accounts
        self.run = run
        self.on_removed = on_removed
        self.on_network = on_network
        self.waiting: WaitDialog | None = None

    def start(self, account: Account) -> None:
        summary = self.accounts.removal_summary(account.id)
        if not confirm(self.parent, presenters.removal_confirmation(summary)):
            return
        self.waiting = WaitDialog(self.parent, text.REMOVING_ACCOUNT)
        run_in_background(
            self.parent,
            lambda: self.run(account.id),
            lambda ok, value: self._done(account, ok, value),
        )

    def _done(self, account: Account, ok: bool, value: Any) -> None:
        if self.waiting is not None:
            self.waiting.destroy()
            self.waiting = None
        self.on_removed()
        if ok:
            if value.revoked:  # the permission was withdrawn over the network
                self.on_network(None)
            show_info(self.parent, presenters.removal_result_message(account, value))
        else:
            show_error(self.parent, user_error(value))


class StoreChoiceDialog(ModalDialog):
    """Without keyring: create a master password or use session mode (F10-2).

    ``result`` is ``("password", <password>)``, ``("session", None)`` or ``None``.
    """

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, text.STORE_CHOICE_TITLE)
        self.choice = tk.StringVar(value="password")
        self.password = tk.StringVar()
        self.repeat = tk.StringVar()
        ttk.Label(self.body, text=text.STORE_CHOICE_INTRO, wraplength=440).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        self.password_option = ttk.Radiobutton(
            self.body, text=text.CHOICE_PASSWORD, value="password", variable=self.choice,
            command=self._update,
        )
        self.password_option.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Label(self.body, text=text.CHOICE_PASSWORD_HINT, wraplength=420).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=(20, 0)
        )
        ttk.Label(self.body, text=text.PASSWORD).grid(row=3, column=0, sticky="w", padx=(20, 4))
        self.password_entry = ttk.Entry(self.body, textvariable=self.password, show="•")
        self.password_entry.grid(row=3, column=1, sticky="ew", pady=2)
        ttk.Label(self.body, text=text.PASSWORD_REPEAT).grid(
            row=4, column=0, sticky="w", padx=(20, 4)
        )
        self.repeat_entry = ttk.Entry(self.body, textvariable=self.repeat, show="•")
        self.repeat_entry.grid(row=4, column=1, sticky="ew", pady=2)
        self.session_option = ttk.Radiobutton(
            self.body, text=text.CHOICE_SESSION, value="session", variable=self.choice,
            command=self._update,
        )
        self.session_option.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(self.body, text=text.CHOICE_SESSION_HINT, wraplength=420).grid(
            row=6, column=0, columnspan=2, sticky="w", padx=(20, 0)
        )
        self.error = ttk.Label(self.body, text="", foreground="#b00020")
        self.error.grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        buttons = ttk.Frame(self.body)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text=text.OK, command=self.accept).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text=text.CANCEL, command=self.cancel).pack(side="left")

    def _update(self) -> None:
        state = "normal" if self.choice.get() == "password" else "disabled"
        self.password_entry.configure(state=state)
        self.repeat_entry.configure(state=state)
        self.error.configure(text="")

    def accept(self) -> None:
        if self.choice.get() == "session":
            self.close(("session", None))
            return
        error = presenters.new_password_error(self.password.get(), self.repeat.get())
        if error is not None:
            self.error.configure(text=error)
            return
        self.close(("password", self.password.get()))


def ask_store_choice(
    parent: tk.Misc, db: Database, data_dir: Path
) -> CredentialStore | None:
    """Ask the user without keyring and build the chosen store (F10-2)."""
    choice = StoreChoiceDialog(parent).show()
    if choice is None:
        return None
    return store_from_choice(db, data_dir, choice[1])


class PasswordDialog(ModalDialog):
    """Ask for the master password when the app opens (F10-3, F10-4, F10-5).

    A wrong password can be typed again. "Forgot" deletes the encrypted credentials
    after confirming and asks for a new password. ``result`` is the opened store, or
    ``None`` if the dialog is closed.
    """

    def __init__(self, parent: tk.Misc, data_dir: Path) -> None:
        super().__init__(parent, text.UNLOCK_TITLE)
        self.path = Path(data_dir) / CREDENTIALS_FILE_NAME
        self.password = tk.StringVar()
        self.repeat = tk.StringVar()
        self.creating = False

        self.intro = ttk.Label(self.body, text=text.UNLOCK_INTRO, wraplength=380)
        self.intro.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(self.body, text=text.PASSWORD).grid(row=1, column=0, sticky="w", padx=(0, 4))
        self.password_entry = ttk.Entry(self.body, textvariable=self.password, show="•")
        self.password_entry.grid(row=1, column=1, sticky="ew", pady=2)
        self.password_entry.bind("<Return>", lambda _: self.accept())
        self.repeat_label = ttk.Label(self.body, text=text.PASSWORD_REPEAT)
        self.repeat_entry = ttk.Entry(self.body, textvariable=self.repeat, show="•")
        self.error = ttk.Label(self.body, text="", foreground="#b00020", wraplength=380)
        self.error.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        buttons = ttk.Frame(self.body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.forgot_button = ttk.Button(buttons, text=text.FORGOT_PASSWORD, command=self.forgot)
        self.forgot_button.pack(side="left")
        self.accept_button = ttk.Button(buttons, text=text.UNLOCK_BUTTON, command=self.accept)
        self.accept_button.pack(side="right")

    def accept(self) -> None:
        if self.creating:
            self._create()
        else:
            self._unlock()

    def _unlock(self) -> None:
        try:
            store = EncryptedFileStore.open(self.path, self.password.get())
        except WrongPasswordError as exc:
            self.error.configure(text=exc.user_message)
            self.password.set("")
            return
        self.close(store)

    def forgot(self) -> None:
        """Reset: the encrypted credentials are deleted, results and states stay (F10-5)."""
        if not confirm(self, text.RESET_CONFIRM):
            return
        EncryptedFileStore.reset(self.path)
        self.creating = True
        self.intro.configure(text=text.NEW_PASSWORD_INTRO)
        self.repeat_label.grid(row=2, column=0, sticky="w", padx=(0, 4))
        self.repeat_entry.grid(row=2, column=1, sticky="ew", pady=2)
        self.forgot_button.pack_forget()
        self.accept_button.configure(text=text.OK)
        self.password.set("")
        self.error.configure(text="")

    def _create(self) -> None:
        error = presenters.new_password_error(self.password.get(), self.repeat.get())
        if error is not None:
            self.error.configure(text=error)
            return
        self.close(EncryptedFileStore.create(self.path, self.password.get()))


class SettingsDialog(ModalDialog):
    """Session mode setting (F10-6).

    Turning it on, after confirming, deletes the saved credentials; the accounts must be
    reconnected. Turning it off takes effect the next time the app opens.
    """

    def __init__(self, parent: tk.Misc, accounts: AccountService, data_dir: Path) -> None:
        super().__init__(parent, text.SETTINGS_TITLE)
        self.accounts = accounts
        self.data_dir = Path(data_dir)
        self.session = tk.BooleanVar(value=session_mode(accounts.db))
        self.session_check = ttk.Checkbutton(
            self.body, text=text.SESSION_MODE, variable=self.session, command=self.toggle
        )
        self.session_check.pack(anchor="w")
        ttk.Label(self.body, text=text.SESSION_MODE_HINT, wraplength=420).pack(
            anchor="w", padx=(20, 0), pady=(2, 0)
        )
        ttk.Button(self.body, text=text.CLOSE, command=self.cancel).pack(anchor="e", pady=(10, 0))

    def toggle(self) -> None:
        db = self.accounts.db
        if not self.session.get():
            set_session_mode(db, False)
            show_info(self, text.SESSION_OFF_DONE)
            return
        if not confirm(self, text.SESSION_ON_CONFIRM):
            self.session.set(False)
            return
        try:
            store = enable_session_mode(
                db, self.data_dir, self.accounts.store, self.accounts.credential_keys()
            )
        except Exception as exc:  # noqa: BLE001 - every failure must reach the user
            self.session.set(False)
            show_error(self, user_error(exc))
            return
        self.accounts.store = store
        show_info(self, text.SESSION_ON_DONE)
