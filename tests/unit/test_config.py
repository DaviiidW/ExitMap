from pathlib import Path

from exitmap.config import data_dir

HOME = Path("/home/user")


def test_linux_uses_xdg_data_home():
    path = data_dir(platform="linux", env={"XDG_DATA_HOME": "/custom/data"}, home=HOME)
    assert path == Path("/custom/data/exitmap")


def test_linux_falls_back_to_local_share():
    assert data_dir(platform="linux", env={}, home=HOME) == HOME / ".local/share/exitmap"


def test_linux_empty_xdg_data_home_is_ignored():
    path = data_dir(platform="linux", env={"XDG_DATA_HOME": ""}, home=HOME)
    assert path == HOME / ".local/share/exitmap"


def test_windows_uses_appdata():
    path = data_dir(platform="win32", env={"APPDATA": "/appdata/Roaming"}, home=HOME)
    assert path == Path("/appdata/Roaming/ExitMap")


def test_windows_without_appdata_uses_default_roaming():
    assert data_dir(platform="win32", env={}, home=HOME) == HOME / "AppData/Roaming/ExitMap"


def test_windows_ignores_xdg_data_home():
    env = {"APPDATA": "/appdata/Roaming", "XDG_DATA_HOME": "/custom/data"}
    assert data_dir(platform="win32", env=env, home=HOME) == Path("/appdata/Roaming/ExitMap")
