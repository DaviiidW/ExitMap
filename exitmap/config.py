"""Application configuration: per-OS data directory."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

LINUX_DIR_NAME = "exitmap"
WINDOWS_DIR_NAME = "ExitMap"
DATA_DIR_MODE = 0o700


def _is_windows(platform: str) -> bool:
    return platform.startswith("win")


def data_dir(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the data directory path for the current (or given) OS.

    Linux: ``$XDG_DATA_HOME/exitmap`` or ``~/.local/share/exitmap``.
    Windows: ``%APPDATA%\\ExitMap``.
    """
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    home = Path.home() if home is None else home

    if _is_windows(platform):
        appdata = env.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / WINDOWS_DIR_NAME

    xdg = env.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / LINUX_DIR_NAME


def ensure_data_dir(path: Path | None = None, platform: str | None = None) -> Path:
    """Create the data directory if needed; on Linux restrict it to the owner (0700)."""
    platform = sys.platform if platform is None else platform
    path = data_dir(platform=platform) if path is None else path

    path.mkdir(parents=True, exist_ok=True)
    if not _is_windows(platform):
        # chmod after mkdir: mkdir's mode is masked by umask and ignored if the dir exists.
        os.chmod(path, DATA_DIR_MODE)
    return path
