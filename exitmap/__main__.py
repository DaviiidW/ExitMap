"""Entry point for ``python -m exitmap`` (plan §2, §3 "Marca de interrupción", §8).

Start order: data directory, logging, database, credential store (asking for the master
password if needed), main window and, if the last analysis was interrupted, the notice.
"""

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from exitmap.config import ensure_data_dir
from exitmap.logging_setup import setup_logging
from exitmap.ui import strings_es as text

if TYPE_CHECKING:  # tkinter may be missing; it is imported in main()
    import tkinter as tk

    from keyring.backend import KeyringBackend

    from exitmap.storage.db import Database
    from exitmap.ui.main_window import MainWindow

DB_FILE_NAME = "exitmap.db"

logger = logging.getLogger("exitmap")


@dataclass
class App:
    db: "Database"
    window: "MainWindow"


def build_app(
    root: "tk.Tk", data_dir: Path, backend: "KeyringBackend | None" = None
) -> App | None:
    """Open the database and the credential store and show the main window.

    Returns ``None`` if the user closes the master password dialog.
    """
    from exitmap.app.accounts import AccountService
    from exitmap.app.analysis import AnalysisService, take_interrupted_mark
    from exitmap.app.services import ServiceCatalogue
    from exitmap.app.unsubscribe import SystemOpener, UnsubscribeService
    from exitmap.storage.credentials import StoreNeed, choose_store
    from exitmap.storage.db import Database
    from exitmap.ui import dialogs
    from exitmap.ui.main_window import MainWindow

    db_path = data_dir / DB_FILE_NAME
    db = Database(db_path)
    decision = choose_store(db, data_dir, backend)
    store = decision.store
    if decision.need is StoreNeed.PASSWORD:  # F10-3
        store = dialogs.PasswordDialog(root, data_dir).show()
        if store is None:
            db.close()
            return None
    # StoreNeed.CHOICE: the store is chosen before connecting the first account (F10-2).

    opener = SystemOpener()
    accounts = AccountService(db, store)
    window = MainWindow(
        root,
        accounts,
        ServiceCatalogue(db, opener),
        connect_runner=dialogs.background_connect(accounts, db_path),
        opener=opener,
        analysis=AnalysisService(db_path),
        unsubscribe=UnsubscribeService(db, opener=opener),
        remove_runner=dialogs.background_remove(accounts, db_path),
        data_dir=data_dir,
    )
    window.pack(fill="both", expand=True)
    root.deiconify()
    if take_interrupted_mark(db):  # F2-6
        dialogs.show_info(root, text.ANALYSIS_INTERRUPTED)
    return App(db, window)


def main() -> int:
    try:
        import tkinter as tk
    except ImportError:
        print(text.NO_TKINTER, file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError:
        print(text.NO_DISPLAY, file=sys.stderr)
        return 1

    data_dir = ensure_data_dir()
    setup_logging(data_dir)
    logger.info("ExitMap started")
    root.title(text.APP_TITLE)
    root.withdraw()
    app = build_app(root, data_dir)
    if app is None:
        root.destroy()
        return 0
    try:
        root.mainloop()
    finally:
        app.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
