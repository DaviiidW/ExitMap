"""Shortcut creation by the installation script (T043; plan §2 "Arranque con icono", §8)."""

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from install_script import install


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(install.Path, "home", classmethod(lambda cls: home))
    return home


def test_linux_entry_goes_to_applications_menu_and_desktop(home, tmp_path):
    desktop = home / "Escritorio"
    desktop.mkdir()
    venv_dir = tmp_path / "repo with spaces" / ".venv"
    paths = install.install_linux_shortcut(venv_dir, venv_dir.parent, home, desktop)
    menu_entry = home / ".local" / "share" / "applications" / "exitmap.desktop"
    assert paths == [menu_entry, desktop / "exitmap.desktop"]
    for path in paths:
        assert stat.S_IMODE(path.stat().st_mode) == 0o755
        content = path.read_text(encoding="utf-8")
        assert f'Exec="{venv_dir / "bin" / "python"}" "-m" "exitmap"' in content
        assert f"Icon={install.ICON_PNG}" in content


def test_linux_entry_respects_xdg_data_home_and_missing_desktop(home, tmp_path, monkeypatch):
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    paths = install.install_linux_shortcut(tmp_path / ".venv", tmp_path, home, None)
    assert paths == [data_home / "applications" / "exitmap.desktop"]


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-validate missing")
def test_linux_entry_is_a_valid_desktop_file(home, tmp_path):
    (path,) = install.install_linux_shortcut(tmp_path / "a b" / ".venv", tmp_path, home, None)
    result = subprocess.run(
        ["desktop-file-validate", str(path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_linux_desktop_dir_uses_xdg_user_dir(home, monkeypatch):
    desktop = home / "Escritorio"
    desktop.mkdir()
    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/bin/xdg-user-dir")
    monkeypatch.setattr(
        install.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=f"{desktop}\n"),
    )
    assert install.linux_desktop_dir(home) == desktop


def test_linux_desktop_dir_ignores_home_and_falls_back_to_desktop(home, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/bin/xdg-user-dir")
    monkeypatch.setattr(
        install.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=f"{home}\n"),
    )
    assert install.linux_desktop_dir(home) is None
    (home / "Desktop").mkdir()
    assert install.linux_desktop_dir(home) == home / "Desktop"


def test_install_shortcut_on_linux_reports_the_created_files(home, monkeypatch, capsys):
    monkeypatch.setattr(install.shutil, "which", lambda name: None)
    assert install.install_shortcut("linux", home / ".venv", home)
    out = capsys.readouterr().out
    assert str(home / ".local" / "share" / "applications" / "exitmap.desktop") in out


def test_install_shortcut_on_windows_runs_powershell(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args, 0, stdout="C:\\Users\\Ana\\Desktop\\ExitMap.lnk\nC:\\Start\\ExitMap.lnk\n"
        )

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    venv_dir = tmp_path / ".venv"
    assert install.install_shortcut("win32", venv_dir, tmp_path)
    assert calls[0][0] == "powershell.exe"
    assert str(venv_dir / "Scripts" / "pythonw.exe") in calls[0][-1]
    assert "ExitMap.lnk" in capsys.readouterr().out


def test_failed_shortcut_explains_how_to_start_by_hand(tmp_path, monkeypatch, capsys):
    def failing_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(install.subprocess, "run", failing_run)
    venv_dir = tmp_path / ".venv"
    assert not install.install_shortcut("win32", venv_dir, tmp_path)
    err = capsys.readouterr().err
    assert f'"{venv_dir / "Scripts" / "python.exe"}" -m exitmap' in err


def test_other_systems_get_the_manual_command(tmp_path, capsys):
    assert not install.install_shortcut("darwin", tmp_path / ".venv", tmp_path)
    assert "-m exitmap" in capsys.readouterr().out


def test_main_installs_and_creates_the_shortcut(monkeypatch, capsys):
    steps = []
    monkeypatch.setattr(install, "create_venv", lambda d: steps.append("venv"))
    monkeypatch.setattr(install, "install_package", lambda d, r: steps.append("pip"))
    monkeypatch.setattr(install, "install_shortcut", lambda p, d, r: steps.append("link"))
    assert install.main() == 0
    assert steps == ["venv", "pip", "link"]


def test_main_stops_with_a_message_if_pip_fails(monkeypatch, capsys):
    def failing_install(venv_dir, repo_dir):
        raise subprocess.CalledProcessError(1, "pip")

    monkeypatch.setattr(install, "create_venv", lambda d: None)
    monkeypatch.setattr(install, "install_package", failing_install)
    assert install.main() == 1
    assert install.MSG_INSTALL_FAILED in capsys.readouterr().err


def test_main_rejects_old_python(monkeypatch, capsys):
    monkeypatch.setattr(install.sys, "version_info", (3, 10, 0))
    assert install.main() == 1
    assert "3.11" in capsys.readouterr().err


def test_create_venv_and_install_package_use_the_venv_python(tmp_path, monkeypatch):
    created, runs = [], []
    monkeypatch.setattr(install.venv, "create", lambda d, with_pip: created.append(d))
    monkeypatch.setattr(install.subprocess, "run", lambda args, check: runs.append(args))
    install.create_venv(tmp_path / ".venv")
    install.install_package(tmp_path / ".venv", tmp_path)
    assert created == [tmp_path / ".venv"]
    python = install.venv_python(tmp_path / ".venv", windows=install.os.name == "nt")
    assert runs == [[str(python), "-m", "pip", "install", "-e", str(tmp_path)]]


def test_icons_exist():
    assert install.ICON_PNG.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert install.ICON_ICO.read_bytes()[:4] == b"\x00\x00\x01\x00"
