"""Smoke test of the main window with a populated database (spec F3, F8-4).

Skipped where Tk has no screen.
"""

import pytest
from fakes import FakeMailProvider

from exitmap.app.accounts import AccountService
from exitmap.app.analysis import analyse, save_analysis
from exitmap.app.services import ServiceCatalogue
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import Account, Provider, RelationType, State
from exitmap.storage.db import Database
from exitmap.ui import strings_es as text
from exitmap.ui.main_window import ALERT_TAG, MainWindow

GMAIL = "ana.prueba@gmail.com"
OUTLOOK = "ana.prueba@outlook.com"


@pytest.fixture
def db(tmp_path):
    catalog = load_catalog(CATALOG_PATH)
    with Database(tmp_path / "exitmap.db") as db:
        for provider, email in ((Provider.GMAIL, GMAIL), (Provider.OUTLOOK, OUTLOOK)):
            account = db.add_account(Account(provider, email))
            save_analysis(db, account.id, analyse(FakeMailProvider(email), account_id=account.id,
                                                  catalog=catalog))
        yield db


@pytest.fixture
def window(tk_root, db):
    window = MainWindow(tk_root, AccountService(db, None), ServiceCatalogue(db))
    window.pack(fill="both", expand=True)
    tk_root.update_idletasks()
    return window


def _names(window):
    return [window.tree.set(iid, "name") for iid in window.tree.get_children()]


def test_lists_accounts_and_services(window, db):
    assert window.account_list.get(0, "end") == (f"{GMAIL} (Gmail)", f"{OUTLOOK} (Outlook)")
    assert len(window.tree.get_children()) == len(db.list_services())
    assert _names(window).count("Spotify") == 2  # F3-1
    assert window.message.cget("text") == ""


def test_search_and_filters_update_the_list(window, db):
    """F3-3, F3-4, F3-5."""
    window.search.set("spot")
    assert _names(window) == ["Spotify", "Spotify"]

    window.account_filter.current(1)
    window.refresh_services()
    assert [window.tree.set(i, "account") for i in window.tree.get_children()] == [GMAIL]

    window.relation_filter.current(3)  # access
    window.refresh_services()
    assert window.criteria().relation_type is RelationType.ACCESS
    assert _names(window) == []
    assert window.message.cget("text") == text.NO_MATCHES


def test_alert_is_highlighted_and_first(window, db):
    """F3-2, F8-4."""
    bbc = next(s for s in db.list_services() if s.domain == "bbc.co.uk")
    db.set_state(bbc.id, State.UNSUBSCRIBED)
    db.set_alert(bbc.id)

    window.refresh()

    first = window.tree.get_children()[0]
    assert first == str(bbc.id)
    assert ALERT_TAG in window.tree.item(first, "tags")
    assert window.tree.set(first, "name") == text.ALERT_MARK + "BBC"
    assert window.message.cget("text") == text.ALERT_HINT


def test_without_accounts_says_so(tk_root, tmp_path):
    with Database(tmp_path / "empty.db") as db:
        window = MainWindow(tk_root, AccountService(db, None), ServiceCatalogue(db))
        assert window.account_list.size() == 0
        assert window.no_accounts.winfo_manager() == "grid"
        assert window.tree.get_children() == ()
