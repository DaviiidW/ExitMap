"""Service page with a populated database and a fake opener (spec F4, F5, F6, F7, F8-5).

Skipped where Tk has no screen.
"""

import pytest
from fakes import FakeMailProvider, FakeOpener

from exitmap.app.accounts import AccountService
from exitmap.app.analysis import analyse, save_analysis
from exitmap.app.services import ServiceCatalogue
from exitmap.app.unsubscribe import UnsubscribeService
from exitmap.domain.catalog import CATALOG_PATH, load_catalog
from exitmap.domain.models import Account, Provider, State
from exitmap.errors import OfflineError
from exitmap.storage.db import Database
from exitmap.ui import dialogs
from exitmap.ui import strings_es as text
from exitmap.ui.main_window import MainWindow
from exitmap.ui.service_detail import ServiceDetailWindow

GMAIL = "ana.prueba@gmail.com"


class FakeHttp:
    def __init__(self, error=None):
        self.error = error
        self.posts = []

    def post_form(self, url, form):
        self.posts.append(url)
        if self.error:
            raise self.error
        return 200


class Prompts:
    def __init__(self, answer):
        self.answer = answer
        self.confirms, self.infos, self.errors = [], [], []


@pytest.fixture
def prompts(monkeypatch):
    shown = Prompts(answer=False)

    def confirm(parent, message):
        shown.confirms.append(message)
        return shown.answer

    monkeypatch.setattr(dialogs, "confirm", confirm)
    monkeypatch.setattr(dialogs, "show_info", lambda p, m: shown.infos.append(m))
    monkeypatch.setattr(dialogs, "show_error", lambda p, e: shown.errors.append(e))
    return shown


@pytest.fixture
def db(tmp_path):
    with Database(tmp_path / "exitmap.db") as db:
        account = db.add_account(Account(Provider.GMAIL, GMAIL))
        save_analysis(db, account.id, analyse(FakeMailProvider(GMAIL), account_id=account.id,
                                              catalog=load_catalog(CATALOG_PATH)))
        yield db


def _page(tk_root, db, domain, http=None, opener=None):
    opener = opener or FakeOpener()
    http = http or FakeHttp()
    service = next(s for s in db.list_services() if s.domain == domain)
    changes = []
    page = ServiceDetailWindow(tk_root, service.id, ServiceCatalogue(db, opener),
                               UnsubscribeService(db, http, opener), lambda: changes.append(1))
    return page, service, opener, http, changes


def test_page_shows_data_evidence_and_link_origin(tk_root, db):
    """F4-1, F4-2, F4-4."""
    page, service, *_ = _page(tk_root, db, "tienda-ejemplo.es")
    values = {label: widget.cget("text") for label, widget in page.field_values.items()}
    assert values[text.FIELD_NAME] == "Tienda Ejemplo"
    assert values[text.FIELD_ACCOUNT] == GMAIL
    assert values[text.FIELD_MANAGE_URL].endswith("(origen: correo)")
    assert len(page.evidence.get_children()) == len(db.list_evidence(service.id)) > 0
    assert str(page.unsubscribe_button.cget("state")) == "normal"


def test_opening_the_page_removes_the_alert(tk_root, db):
    """F8-5."""
    bbc = next(s for s in db.list_services() if s.domain == "bbc.co.uk")
    db.set_alert(bbc.id)
    page, _, _, _, changes = _page(tk_root, db, "bbc.co.uk")
    assert not db.get_service(bbc.id).has_alert
    assert changes == [1]


def test_without_subscription_unsubscribe_is_disabled(tk_root, db):
    page, *_ = _page(tk_root, db, "github.com")
    assert str(page.unsubscribe_button.cget("state")) == "disabled"
    assert str(page.delete_button.cget("state")) == "normal"


@pytest.mark.parametrize("domain", ["spotify.com", "amazon.es", "bbc.co.uk"])
def test_cancelling_the_unsubscribe_does_nothing(tk_root, db, prompts, domain):
    """F5-1, F5-6."""
    page, service, opener, http, _ = _page(tk_root, db, domain)
    page.unsubscribe_button.invoke()
    assert len(prompts.confirms) == 1 and GMAIL in prompts.confirms[0]
    assert opener.urls == opener.mails == http.posts == []
    assert db.get_service(service.id).state is State.PENDING
    assert prompts.infos == []


@pytest.mark.parametrize("button", ["delete_button", "revoke_button"])
def test_cancelling_the_management_link_does_nothing(tk_root, db, prompts, button):
    page, service, opener, *_ = _page(tk_root, db, "github.com")
    getattr(page, button).invoke()
    assert len(prompts.confirms) == 1 and opener.urls == []


def test_one_click_unsubscribe_changes_the_state(tk_root, db, prompts):
    """F5-2."""
    prompts.answer = True
    page, service, opener, http, _ = _page(tk_root, db, "spotify.com")
    page.unsubscribe_button.invoke()
    assert http.posts == [service.unsubscribe_target]
    assert db.get_service(service.id).state is State.UNSUBSCRIBED
    assert page.state_box.get() == "Baja realizada"
    assert "Baja realizada" in prompts.infos[0]


def test_failed_one_click_opens_the_web_and_keeps_the_state(tk_root, db, prompts):
    """F5-3."""
    prompts.answer = True
    page, service, opener, http, _ = _page(tk_root, db, "spotify.com", FakeHttp(OfflineError()))
    page.unsubscribe_button.invoke()
    assert opener.urls == [service.unsubscribe_target]
    assert db.get_service(service.id).state is State.PENDING
    assert prompts.infos[0].startswith(OfflineError().problem)


def test_web_and_mail_unsubscribe_keep_the_state(tk_root, db, prompts):
    """F5-4, F5-5."""
    prompts.answer = True
    page, amazon, opener, *_ = _page(tk_root, db, "amazon.es")
    page.unsubscribe_button.invoke()
    assert opener.urls == [amazon.unsubscribe_target]
    page, bbc, opener, *_ = _page(tk_root, db, "bbc.co.uk")
    page.unsubscribe_button.invoke()
    assert len(opener.mails) == 1
    assert {db.get_service(s.id).state for s in (amazon, bbc)} == {State.PENDING}
    assert prompts.infos == [text.UNSUBSCRIBE_WEB_OPENED, text.UNSUBSCRIBE_MAIL_PREPARED]


def test_confirmed_management_link_opens_without_changing_the_state(tk_root, db, prompts):
    """F6-1, F6-2."""
    prompts.answer = True
    page, service, opener, *_ = _page(tk_root, db, "github.com")
    page.revoke_button.invoke()
    assert opener.urls == [service.manage_url]
    assert db.get_service(service.id).state is State.PENDING


def test_state_selector(tk_root, db):
    """F7-2."""
    page, service, _, _, changes = _page(tk_root, db, "github.com")
    page.state_box.current(list(State).index(State.DISMISSED))
    page.change_state()
    assert db.get_service(service.id).state is State.DISMISSED
    assert page.field_values[text.FIELD_STATE].cget("text") == "Descartado"
    assert changes == [1, 1]


def test_main_window_opens_the_selected_service(tk_root, db):
    window = MainWindow(tk_root, AccountService(db, None), ServiceCatalogue(db))
    assert window.open_selected_service() is None
    first = window.tree.get_children()[0]
    window.tree.selection_set(first)
    page = window.open_selected_service()
    assert page.service_id == int(first)
