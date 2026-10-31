"""Main window: connected accounts, search, filters and the service list (spec F3, F8-4).

Thin widgets: what is shown comes from ``app.services`` and ``ui.presenters``.
"""

import tkinter as tk
from tkinter import font, ttk

from exitmap.app.accounts import AccountService
from exitmap.app.services import ServiceCatalogue, ServiceFilter
from exitmap.domain.models import Service
from exitmap.ui import presenters
from exitmap.ui import strings_es as text

COLUMNS = (
    ("name", text.COLUMN_NAME, 220),
    ("domain", text.COLUMN_DOMAIN, 160),
    ("account", text.COLUMN_ACCOUNT, 200),
    ("relations", text.COLUMN_RELATIONS, 260),
    ("state", text.COLUMN_STATE, 130),
)
ALERT_TAG = "alert"
ALERT_BACKGROUND = "#ffe08a"


class MainWindow(ttk.Frame):
    """Accounts panel on the left; search, filters and list on the right."""

    def __init__(
        self, master: tk.Misc, accounts: AccountService, catalogue: ServiceCatalogue
    ) -> None:
        super().__init__(master, padding=8)
        self.accounts = accounts
        self.catalogue = catalogue
        self._account_options: list[tuple[str, int | None]] = []
        self._relation_options = presenters.relation_filter_options()
        self._state_options = presenters.state_filter_options()
        self.services: list[Service] = []

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_accounts_panel()
        self._build_services_panel()
        self.refresh()

    # Layout -----------------------------------------------------------------------------

    def _build_accounts_panel(self) -> None:
        panel = ttk.LabelFrame(self, text=text.ACCOUNTS_TITLE, padding=6)
        panel.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        panel.rowconfigure(0, weight=1)
        self.account_list = tk.Listbox(panel, width=34, activestyle="none", exportselection=False)
        self.account_list.grid(row=0, column=0, sticky="ns")
        self.no_accounts = ttk.Label(panel, text=text.NO_ACCOUNTS)

    def _build_services_panel(self) -> None:
        panel = ttk.Frame(self)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        bar = ttk.Frame(panel)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(bar, text=text.SEARCH_LABEL).pack(side="left")
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(bar, textvariable=self.search, width=28)
        self.search_entry.pack(side="left", padx=(4, 8))
        self.search.trace_add("write", lambda *_: self.refresh_services())
        self.account_filter = self._combobox(bar, 26)
        self.relation_filter = self._combobox(bar, 24)
        self.state_filter = self._combobox(bar, 18)
        self._set_options(self.relation_filter, self._relation_options)
        self._set_options(self.state_filter, self._state_options)

        # Rows as tall as the font, so they are not clipped on scaled screens.
        row_height = font.nametofont("TkDefaultFont").metrics("linespace") + 6
        ttk.Style(self).configure("Treeview", rowheight=row_height)
        self.tree = ttk.Treeview(
            panel, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse"
        )
        for key, heading, width in COLUMNS:
            self.tree.heading(key, text=heading, anchor="w")
            self.tree.column(key, width=width, anchor="w")
        self.tree.tag_configure(ALERT_TAG, background=ALERT_BACKGROUND)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        self.message = ttk.Label(panel, text="")
        self.message.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _combobox(self, parent: tk.Misc, width: int) -> ttk.Combobox:
        box = ttk.Combobox(parent, state="readonly", width=width)
        box.pack(side="left", padx=(0, 6))
        box.bind("<<ComboboxSelected>>", lambda _: self.refresh_services())
        return box

    @staticmethod
    def _set_options(box: ttk.Combobox, options: list[tuple[str, object]]) -> None:
        current = box.current()
        box.configure(values=[label for label, _ in options])
        box.current(current if 0 <= current < len(options) else 0)

    # Data -------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload accounts and services, keeping the search and filters."""
        self.refresh_accounts()
        self.refresh_services()

    def refresh_accounts(self) -> None:
        accounts = self.accounts.list_accounts()
        self._accounts = {a.id: a for a in accounts}
        self.account_list.delete(0, "end")
        for account in accounts:
            self.account_list.insert("end", presenters.account_label(account))
        if accounts:
            self.no_accounts.grid_remove()
        else:
            self.no_accounts.grid(row=1, column=0, sticky="w")
        self._account_options = presenters.account_filter_options(accounts)
        self._set_options(self.account_filter, self._account_options)

    def criteria(self) -> ServiceFilter:
        """Search text and filters chosen in the window (F3-3, F3-4)."""
        return ServiceFilter(
            text=self.search.get(),
            account_id=self._account_options[self.account_filter.current()][1],
            relation_type=self._relation_options[self.relation_filter.current()][1],
            state=self._state_options[self.state_filter.current()][1],
        )

    def refresh_services(self) -> None:
        criteria = self.criteria()
        self.services = self.catalogue.list(criteria)
        self.tree.delete(*self.tree.get_children())
        for service in self.services:
            self.tree.insert(
                "",
                "end",
                iid=str(service.id),
                values=presenters.service_row(service, self._accounts),
                tags=(ALERT_TAG,) if service.has_alert else (),
            )
        message = presenters.list_message(len(self.services), presenters.is_filtered(criteria))
        if message is None and any(s.has_alert for s in self.services):
            message = text.ALERT_HINT
        self.message.configure(text=message or "")

