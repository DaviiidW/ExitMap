"""Shared fixtures."""

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
