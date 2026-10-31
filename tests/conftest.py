"""Shared fixtures."""

import gc

import pytest


@pytest.fixture
def tk_root():
    """A hidden Tk root; the test is skipped where there is no screen (plan §6 "UI")."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No screen available for Tk")
    root.withdraw()
    yield root
    root.destroy()
    # Free Tk objects here: if a background thread collects them, Tk complains.
    gc.collect()
