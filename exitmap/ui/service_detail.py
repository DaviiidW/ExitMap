"""Service page: data, evidence, link origin, actions and state (spec F4, F5, F6, F7).

Every action asks for confirmation first and does nothing if it is cancelled
(F5-1, F5-6; constitution 8). Opening the page removes the alert (F8-5).
"""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from exitmap.app.services import ServiceCatalogue, ServiceDetail
from exitmap.app.unsubscribe import Outcome, UnsubscribeService
from exitmap.domain.models import State, UnsubscribeMethod
from exitmap.ui import dialogs, presenters
from exitmap.ui import strings_es as text

EVIDENCE_COLUMNS = (
    ("subject", text.EVIDENCE_SUBJECT, 380),
    ("date", text.EVIDENCE_DATE, 110),
    ("relation", text.EVIDENCE_RELATION, 200),
)


class ServiceDetailWindow(tk.Toplevel):
    """Page of one service; ``on_change`` runs after anything that changes the list."""

    def __init__(
        self,
        parent: tk.Misc,
        service_id: int,
        catalogue: ServiceCatalogue,
        unsubscribe: UnsubscribeService,
        on_change: Callable[[], None] = lambda: None,
        on_network: Callable[[BaseException | None], None] = lambda error: None,
    ) -> None:
        super().__init__(parent)
        self.on_network = on_network
        self.transient(parent.winfo_toplevel())
        self.service_id = service_id
        self.catalogue = catalogue
        self.unsubscribe_service = unsubscribe
        self.on_change = on_change
        self._states = list(State)

        self.detail: ServiceDetail = catalogue.detail(service_id)
        self.title(text.DETAIL_TITLE.format(service=self.detail.service.name))
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        self.fields = ttk.Frame(body)
        self.fields.grid(row=0, column=0, sticky="ew")
        self.field_values: dict[str, ttk.Label] = {}

        actions = ttk.Frame(body)
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.unsubscribe_button = ttk.Button(
            actions, text=text.UNSUBSCRIBE_BUTTON, command=self.unsubscribe
        )
        self.unsubscribe_button.pack(side="left", padx=(0, 6))
        self.delete_button = ttk.Button(
            actions,
            text=text.DELETE_ACCOUNT_BUTTON,
            command=lambda: self.open_management(text.DELETE_ACCOUNT_ACTION),
        )
        self.delete_button.pack(side="left", padx=(0, 6))
        self.revoke_button = ttk.Button(
            actions,
            text=text.REVOKE_ACCESS_BUTTON,
            command=lambda: self.open_management(text.REVOKE_ACCESS_ACTION),
        )
        self.revoke_button.pack(side="left", padx=(0, 6))
        ttk.Label(actions, text=text.FIELD_STATE + ":").pack(side="left", padx=(12, 4))
        self.state_box = ttk.Combobox(
            actions,
            state="readonly",
            width=18,
            values=[text.STATE_LABELS[s.value] for s in self._states],
        )
        self.state_box.pack(side="left")
        self.state_box.bind("<<ComboboxSelected>>", lambda _: self.change_state())

        ttk.Label(body, text=text.EVIDENCE_TITLE).grid(row=2, column=0, sticky="w", pady=(12, 4))
        dialogs.fit_treeview_rows(self)
        self.evidence = ttk.Treeview(
            body, columns=[c[0] for c in EVIDENCE_COLUMNS], show="headings", height=8
        )
        for key, heading, width in EVIDENCE_COLUMNS:
            self.evidence.heading(key, text=heading, anchor="w")
            self.evidence.column(key, width=width, anchor="w")
        self.evidence.grid(row=3, column=0, sticky="nsew")
        for item in self.detail.evidence:
            self.evidence.insert("", "end", values=presenters.evidence_row(item))

        self._show()
        # The alert was removed when the page was opened (F8-5).
        self.on_change()

    def _show(self) -> None:
        """Fill the fields and the controls from ``self.detail``."""
        for row, (label, value) in enumerate(presenters.detail_fields(self.detail)):
            if label not in self.field_values:
                ttk.Label(self.fields, text=label + ":").grid(
                    row=row, column=0, sticky="nw", padx=(0, 8)
                )
                self.field_values[label] = ttk.Label(self.fields, wraplength=560)
                self.field_values[label].grid(row=row, column=1, sticky="w")
            self.field_values[label].configure(text=value)
        service = self.detail.service
        can_unsubscribe = presenters.can_unsubscribe(service)
        self.unsubscribe_button.configure(state="normal" if can_unsubscribe else "disabled")
        has_link = "normal" if service.manage_url else "disabled"
        self.delete_button.configure(state=has_link)
        self.revoke_button.configure(state=has_link)
        self.state_box.current(self._states.index(service.state))

    def _reload(self) -> None:
        self.detail = self.catalogue.detail(self.service_id)
        self._show()
        self.on_change()

    def unsubscribe(self) -> None:
        """Confirm, then unsubscribe with the method of the service (F5)."""
        service, account = self.detail.service, self.detail.account
        if not dialogs.confirm(self, presenters.unsubscribe_confirmation(service, account)):
            return
        try:
            result = self.unsubscribe_service.unsubscribe(self.service_id)
        except Exception as exc:  # noqa: BLE001 - every failure must reach the user
            dialogs.show_error(self, dialogs.user_error(exc))
            return
        if service.unsubscribe_method is UnsubscribeMethod.ONE_CLICK:
            # The automatic unsubscribe is the only action here that uses the network.
            self.on_network(result.error if result.outcome is Outcome.FAILED_WEB_OPENED else None)
        self._reload()
        dialogs.show_info(self, presenters.unsubscribe_result_message(result, service))

    def open_management(self, action: str) -> None:
        """Confirm, then open the management link; the state does not change (F6)."""
        if not dialogs.confirm(
            self, presenters.management_confirmation(self.detail.service, action)
        ):
            return
        try:
            self.catalogue.open_management(self.service_id)
        except Exception as exc:  # noqa: BLE001 - every failure must reach the user
            dialogs.show_error(self, dialogs.user_error(exc))

    def change_state(self) -> None:
        """Give the service the chosen state (F7-2)."""
        state = self._states[self.state_box.current()]
        if state is not self.detail.service.state:
            self.catalogue.set_state(self.service_id, state)
            self._reload()
