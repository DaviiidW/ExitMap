"""Analysis dialog: options, progress, cancellation and result (spec F2-1..6, F2-9, F2-10,
F8-1, F8-2).

The analysis runs in ``AnalysisService``'s thread; the dialog reads its events with
``after()``. It is not modal, so the list can still be browsed; while it runs the main
window cannot start another one (F2-9).
"""

import queue
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from exitmap.app.analysis import (
    AnalysisMode,
    AnalysisService,
    Cancelled,
    Failed,
    Finished,
    Progress,
)
from exitmap.domain.models import Account
from exitmap.providers.base import MailProvider
from exitmap.ui import presenters
from exitmap.ui import strings_es as text
from exitmap.ui.dialogs import user_error
from exitmap.ui.presenters import MODE_LABELS, PERIOD_LABELS, AnalysisOptions, PeriodChoice

POLL_MS = 100
ERROR_COLOUR = "#b00020"


class AnalysisDialog(tk.Toplevel):
    """Choose what to analyse, follow the progress and see the result.

    ``on_start`` runs when the analysis starts and ``on_end`` when it ends in any way, so
    the main window can block a second analysis and reload the list.
    """

    def __init__(
        self,
        parent: tk.Misc,
        accounts: list[Account],
        analysis: AnalysisService,
        provider_for: Callable[[Account], MailProvider],
        selected: Account | None = None,
        on_start: Callable[[], None] = lambda: None,
        on_end: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__(parent)
        self.title(text.ANALYSIS_TITLE)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.accounts = accounts
        self.analysis = analysis
        self.provider_for = provider_for
        self.on_start = on_start
        self.on_end = on_end
        self.running = False
        self.protocol("WM_DELETE_WINDOW", self.close)

        defaults = presenters.default_analysis_options()
        self.period = tk.StringVar(value=defaults.period.value)
        self.start_text = tk.StringVar(value=defaults.start_text)
        self.end_text = tk.StringVar(value=defaults.end_text)
        self.include_spam = tk.BooleanVar(value=defaults.include_spam)
        self.include_trash = tk.BooleanVar(value=defaults.include_trash)
        self.mode = tk.StringVar(value=defaults.mode.value)

        self.options_frame = ttk.Frame(self, padding=12)
        self.options_frame.pack(fill="both", expand=True)
        self._build_options(selected or accounts[0])
        self.progress_frame = ttk.Frame(self, padding=12)
        self._build_progress()

    # Options ----------------------------------------------------------------------------

    def _build_options(self, selected: Account) -> None:
        frame = self.options_frame
        ttk.Label(frame, text=text.ANALYSIS_ACCOUNT).grid(row=0, column=0, sticky="w")
        self.account_box = ttk.Combobox(
            frame,
            state="readonly",
            width=40,
            values=[presenters.account_label(a) for a in self.accounts],
        )
        self.account_box.current(self.accounts.index(selected))
        self.account_box.grid(row=0, column=1, sticky="w")
        self.account_box.bind("<<ComboboxSelected>>", lambda _: self._update_options())

        self.mode_frame = ttk.LabelFrame(frame, text=text.ANALYSIS_MODE, padding=6)
        self.mode_buttons = {
            mode: ttk.Radiobutton(
                self.mode_frame,
                text=label,
                value=mode.value,
                variable=self.mode,
                command=self._update_options,
            )
            for mode, label in MODE_LABELS.items()
        }
        for button in self.mode_buttons.values():
            button.pack(anchor="w")
        self.notice = ttk.Label(self.mode_frame, text="", wraplength=440)
        self.notice.pack(anchor="w", pady=(4, 0))

        period = ttk.LabelFrame(frame, text=text.ANALYSIS_PERIOD, padding=6)
        period.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.period_buttons = {}
        for row, (choice, label) in enumerate(PERIOD_LABELS.items()):
            button = ttk.Radiobutton(
                period,
                text=label,
                value=choice.value,
                variable=self.period,
                command=self._update_options,
            )
            button.grid(row=row, column=0, columnspan=4, sticky="w")
            self.period_buttons[choice] = button
        ttk.Label(period, text=text.ANALYSIS_FROM).grid(row=3, column=0, sticky="w", padx=(20, 4))
        self.start_entry = ttk.Entry(period, textvariable=self.start_text, width=12)
        self.start_entry.grid(row=3, column=1, sticky="w")
        ttk.Label(period, text=text.ANALYSIS_TO).grid(row=3, column=2, sticky="w", padx=(12, 4))
        self.end_entry = ttk.Entry(period, textvariable=self.end_text, width=12)
        self.end_entry.grid(row=3, column=3, sticky="w")

        folders = ttk.LabelFrame(frame, text=text.ANALYSIS_FOLDERS, padding=6)
        folders.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(folders, text=text.INCLUDE_SPAM, variable=self.include_spam).pack(
            anchor="w"
        )
        ttk.Checkbutton(folders, text=text.INCLUDE_TRASH, variable=self.include_trash).pack(
            anchor="w"
        )

        self.error = ttk.Label(frame, text="", foreground=ERROR_COLOUR, wraplength=440)
        self.error.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.start_button = ttk.Button(buttons, text=text.START_ANALYSIS, command=self.start)
        self.start_button.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text=text.CANCEL, command=self.close).pack(side="left")
        self._update_options()

    def account(self) -> Account:
        return self.accounts[self.account_box.current()]

    def options(self) -> AnalysisOptions:
        return AnalysisOptions(
            period=PeriodChoice(self.period.get()),
            start_text=self.start_text.get(),
            end_text=self.end_text.get(),
            include_spam=self.include_spam.get(),
            include_trash=self.include_trash.get(),
            mode=AnalysisMode(self.mode.get()),
        )

    def _update_options(self) -> None:
        """Show the re-analysis choice only after a complete analysis (F8-1, F8-2).

        "New emails only" reads since the last analysis, so the period does not apply.
        """
        account = self.account()
        notice = presenters.reanalysis_notice(account)
        if notice is None:
            self.mode.set(AnalysisMode.ALL.value)
            self.mode_frame.grid_remove()
        else:
            self.notice.configure(text=notice)
            self.mode_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        new_only = presenters.is_reanalysis(account) and self.mode.get() == AnalysisMode.NEW_ONLY
        for button in self.period_buttons.values():
            button.configure(state="disabled" if new_only else "normal")
        custom = not new_only and self.period.get() == PeriodChoice.CUSTOM
        for entry in (self.start_entry, self.end_entry):
            entry.configure(state="normal" if custom else "disabled")
        self.error.configure(text="")

    # Running ----------------------------------------------------------------------------

    def _build_progress(self) -> None:
        frame = self.progress_frame
        self.progress_label = ttk.Label(frame, text=text.ANALYSIS_LISTING)
        self.progress_label.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(frame, length=420, mode="determinate")
        self.progress_bar.pack(fill="x", pady=8)
        self.result = ttk.Label(frame, text="", wraplength=420, justify="left")
        self.result.pack(anchor="w")
        self.progress_button = ttk.Button(frame, text=text.CANCEL, command=self.cancel)
        self.progress_button.pack(anchor="e", pady=(8, 0))

    def start(self) -> None:
        """Start the analysis, unless the options are not valid (F2-2)."""
        account, options = self.account(), self.options()
        try:
            period = presenters.analysis_period(options, account)
            provider = self.provider_for(account)
            self.analysis.start(
                provider,
                account.id,
                period,
                presenters.analysis_folders(options),
                options.mode,
            )
        except Exception as exc:  # noqa: BLE001 - every failure must reach the user
            self.error.configure(text=user_error(exc).user_message)
            return
        self.running = True
        self.options_frame.pack_forget()
        self.progress_frame.pack(fill="both", expand=True)
        self.on_start()
        self.after(POLL_MS, self._poll)

    def _poll(self) -> None:
        while True:
            try:
                event = self.analysis.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, Progress):
                self.progress_bar.configure(maximum=max(event.total, 1), value=event.done)
                self.progress_label.configure(
                    text=presenters.progress_text(event.done, event.total)
                )
            else:
                self._finish(event)
                return
        self.after(POLL_MS, self._poll)

    def _finish(self, event: Finished | Cancelled | Failed) -> None:
        self.running = False
        self.on_end()
        if isinstance(event, Finished):
            message = presenters.analysis_done_message(event.service_count)
        elif isinstance(event, Cancelled):
            message = text.ANALYSIS_CANCELLED
        else:
            message = f"{event.error.user_message}\n\n{text.ANALYSIS_STOPPED}"
        self.result.configure(text=message)
        self.progress_button.configure(text=text.CLOSE, command=self.destroy)

    def cancel(self) -> None:
        """Stop the analysis; its results are discarded (F2-5)."""
        self.progress_button.configure(state="disabled")
        self.analysis.cancel()

    def close(self) -> None:
        """Closing the window while the analysis runs cancels it."""
        if self.running:
            self.cancel()
        else:
            self.destroy()

