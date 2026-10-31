"""Start without tkinter or without a screen (plan §8) and the interruption mark (F2-6)."""

import builtins

from exitmap import __main__ as entry
from exitmap.app.analysis import IN_PROGRESS_KEY, take_interrupted_mark
from exitmap.storage.db import Database
from exitmap.ui import strings_es as text


def test_interrupted_mark_is_reported_once():
    with Database(":memory:") as db:
        assert not take_interrupted_mark(db)
        db.set_setting(IN_PROGRESS_KEY, "1")
        assert take_interrupted_mark(db)
        assert db.get_setting(IN_PROGRESS_KEY) is None
        assert not take_interrupted_mark(db)


def test_without_tkinter_a_clear_message_is_shown(monkeypatch, capsys):
    real_import = builtins.__import__

    def no_tkinter(name, *args, **kwargs):
        if name == "tkinter":
            raise ImportError("No module named '_tkinter'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_tkinter)
    assert entry.main() == 1
    assert text.NO_TKINTER in capsys.readouterr().err


def test_without_screen_a_clear_message_is_shown(monkeypatch, capsys):
    import tkinter

    def no_screen():
        raise tkinter.TclError("no display name")

    monkeypatch.setattr(tkinter, "Tk", no_screen)
    assert entry.main() == 1
    assert text.NO_DISPLAY in capsys.readouterr().err
