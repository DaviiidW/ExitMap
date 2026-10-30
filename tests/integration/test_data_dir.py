import stat
import sys

import pytest

from exitmap.config import ensure_data_dir

linux_only = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


@linux_only
def test_creates_data_dir_from_xdg_with_0700(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    path = ensure_data_dir()

    assert path == tmp_path / "xdg" / "exitmap"
    assert path.is_dir()
    assert _mode(path) == 0o700


@linux_only
def test_existing_dir_permissions_are_tightened(tmp_path):
    path = tmp_path / "exitmap"
    path.mkdir(mode=0o755)
    path.chmod(0o755)

    ensure_data_dir(path)

    assert _mode(path) == 0o700


def test_is_idempotent(tmp_path):
    path = tmp_path / "exitmap"
    (ensure_data_dir(path) / "keep.txt").write_text("x")

    ensure_data_dir(path)

    assert (path / "keep.txt").read_text() == "x"


@linux_only
def test_windows_does_not_change_permissions(tmp_path):
    path = tmp_path / "ExitMap"
    path.mkdir()
    path.chmod(0o755)

    ensure_data_dir(path, platform="win32")

    assert _mode(path) == 0o755
