"""Install ExitMap from the repository and create a shortcut with its icon (plan §2, §8).

Usage, from any folder: ``python scripts/install.py``

Steps:
1. Create ``.venv`` in the repository (if it does not exist yet).
2. Install the package in editable mode, because the app reads ``data/`` and ``docs/``
   from the repository.
3. Create the shortcut:
   - Linux: ``~/.local/share/applications/exitmap.desktop`` and a copy on the desktop.
   - Windows: ``ExitMap.lnk`` on the desktop and in the Start menu, created with
     PowerShell (``WScript.Shell``) and launching ``pythonw.exe -m exitmap`` so that no
     console appears.

Only the standard library is used, because it runs before anything is installed.
"""

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

MIN_PYTHON = (3, 11)
REPO_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = REPO_DIR / ".venv"
ICON_PNG = REPO_DIR / "assets" / "exitmap.png"
ICON_ICO = REPO_DIR / "assets" / "exitmap.ico"
DESKTOP_FILE_NAME = "exitmap.desktop"
SHORTCUT_NAME = "ExitMap.lnk"
APP_NAME = "ExitMap"
APP_COMMENT = "Descubre en qué servicios estás registrado a partir de tu correo"

MSG_OLD_PYTHON = (
    "ExitMap necesita Python {required} o posterior y estás usando Python {current}. "
    "Instala una versión más reciente y vuelve a ejecutar este script."
)
MSG_CREATING_VENV = "Creando el entorno virtual en {path}…"
MSG_INSTALLING = "Instalando ExitMap y sus dependencias…"
MSG_VENV_FAILED = (
    "No se ha podido crear el entorno virtual. En Linux, instala el paquete python3-venv "
    "(por ejemplo, «sudo apt install python3-venv») y vuelve a ejecutar este script."
)
MSG_INSTALL_FAILED = (
    "No se ha podido instalar ExitMap. Comprueba la conexión a internet y vuelve a "
    "ejecutar este script."
)
MSG_SHORTCUT_CREATED = "Acceso directo creado: {path}"
MSG_SHORTCUT_FAILED = (
    "No se ha podido crear el acceso directo. Puedes abrir ExitMap con: {command}"
)
MSG_UNSUPPORTED_OS = (
    "Este sistema no es Linux ni Windows, así que no se crea acceso directo. Puedes abrir "
    "ExitMap con: {command}"
)
MSG_DONE = "ExitMap está instalado."


def venv_python(venv_dir: Path, windows: bool, windowed: bool = False) -> Path:
    """Python of the virtual environment; ``windowed`` gives ``pythonw.exe`` on Windows."""
    if windows:
        return venv_dir / "Scripts" / ("pythonw.exe" if windowed else "python.exe")
    return venv_dir / "bin" / "python"


def launch_command(venv_dir: Path, windows: bool) -> str:
    """Command to open the app by hand, shown when no shortcut can be created."""
    python = venv_python(venv_dir, windows)
    return f'"{python}" -m exitmap'


# --- Linux -------------------------------------------------------------------------------


def _desktop_exec_arg(arg: str) -> str:
    """Quote an ``Exec`` argument (Desktop Entry Specification, "The Exec key").

    Inside double quotes, ``"``, `` ` ``, ``$`` and ``\\`` are escaped with a backslash;
    then every backslash is doubled again, because ``Exec`` is a string value.
    """
    quoted = "".join("\\" + ch if ch in '"`$\\' else ch for ch in arg)
    return '"' + quoted.replace("\\", "\\\\") + '"'


def _desktop_string(value: str) -> str:
    """Escape a string value of a desktop entry (backslash and line breaks)."""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def desktop_entry(python: Path, repo_dir: Path, icon: Path) -> str:
    """Content of ``exitmap.desktop``."""
    exec_line = " ".join(_desktop_exec_arg(a) for a in (str(python), "-m", "exitmap"))
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Comment={_desktop_string(APP_COMMENT)}\n"
        f"Exec={exec_line}\n"
        f"Path={_desktop_string(str(repo_dir))}\n"
        f"Icon={_desktop_string(str(icon))}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
    )


def linux_desktop_dir(home: Path) -> Path | None:
    """User's desktop folder (it may be translated, e.g. ``~/Escritorio``), if it exists."""
    candidates = []
    if shutil.which("xdg-user-dir"):
        result = subprocess.run(
            ["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            candidates.append(Path(result.stdout.strip()))
    candidates.append(home / "Desktop")
    for candidate in candidates:
        # xdg-user-dir returns the home folder when no desktop folder is configured.
        if candidate != home and candidate.is_dir():
            return candidate
    return None


def install_linux_shortcut(
    venv_dir: Path, repo_dir: Path, home: Path, desktop_dir: Path | None
) -> list[Path]:
    """Write the desktop entry in the applications menu and copy it to the desktop."""
    content = desktop_entry(venv_python(venv_dir, windows=False), repo_dir, ICON_PNG)
    data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    targets = [data_home / "applications" / DESKTOP_FILE_NAME]
    if desktop_dir is not None:
        targets.append(desktop_dir / DESKTOP_FILE_NAME)
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        target.chmod(0o755)  # desktop environments only launch executable entries
    return targets


# --- Windows -----------------------------------------------------------------------------


def _ps_literal(value: str) -> str:
    """PowerShell single-quoted string: single quotes are doubled."""
    return "'" + value.replace("'", "''") + "'"


def powershell_script(pythonw: Path, repo_dir: Path, icon: Path) -> str:
    """PowerShell that creates ``ExitMap.lnk`` on the desktop and in the Start menu."""
    return (
        "$ErrorActionPreference = 'Stop'; "
        "$shell = New-Object -ComObject WScript.Shell; "
        "foreach ($folder in @([Environment]::GetFolderPath('Desktop'), "
        "[Environment]::GetFolderPath('Programs'))) { "
        f"$link = $shell.CreateShortcut((Join-Path $folder {_ps_literal(SHORTCUT_NAME)})); "
        f"$link.TargetPath = {_ps_literal(str(pythonw))}; "
        "$link.Arguments = '-m exitmap'; "
        f"$link.WorkingDirectory = {_ps_literal(str(repo_dir))}; "
        f"$link.IconLocation = {_ps_literal(str(icon) + ',0')}; "
        f"$link.Description = {_ps_literal(APP_COMMENT)}; "
        "$link.Save(); "
        "Write-Output $link.FullName "
        "}"
    )


def powershell_command(pythonw: Path, repo_dir: Path, icon: Path) -> list[str]:
    """Arguments to run :func:`powershell_script`."""
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        powershell_script(pythonw, repo_dir, icon),
    ]


def install_windows_shortcut(venv_dir: Path, repo_dir: Path) -> list[Path]:
    """Create the shortcuts with PowerShell; returns their paths."""
    pythonw = venv_python(venv_dir, windows=True, windowed=True)
    result = subprocess.run(
        powershell_command(pythonw, repo_dir, ICON_ICO),
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


# --- Installation ------------------------------------------------------------------------


def create_venv(venv_dir: Path) -> None:
    if venv_python(venv_dir, windows=os.name == "nt").exists():
        return
    print(MSG_CREATING_VENV.format(path=venv_dir), flush=True)
    venv.create(venv_dir, with_pip=True)


def install_package(venv_dir: Path, repo_dir: Path) -> None:
    print(MSG_INSTALLING, flush=True)
    python = venv_python(venv_dir, windows=os.name == "nt")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-e", str(repo_dir)], check=True
    )


def install_shortcut(platform: str, venv_dir: Path, repo_dir: Path) -> bool:
    """Create the shortcut for ``platform`` (``sys.platform``); ``False`` if not possible."""
    windows = platform == "win32"
    command = launch_command(venv_dir, windows)
    try:
        if windows:
            paths = install_windows_shortcut(venv_dir, repo_dir)
        elif platform.startswith("linux"):
            home = Path.home()
            paths = install_linux_shortcut(
                venv_dir, repo_dir, home, linux_desktop_dir(home)
            )
        else:
            print(MSG_UNSUPPORTED_OS.format(command=command))
            return False
    except (OSError, subprocess.CalledProcessError):
        print(MSG_SHORTCUT_FAILED.format(command=command), file=sys.stderr)
        return False
    for path in paths:
        print(MSG_SHORTCUT_CREATED.format(path=path))
    return True


def main() -> int:
    if sys.version_info < MIN_PYTHON:
        print(
            MSG_OLD_PYTHON.format(
                required=".".join(map(str, MIN_PYTHON)),
                current=".".join(map(str, sys.version_info[:3])),
            ),
            file=sys.stderr,
        )
        return 1
    try:
        create_venv(VENV_DIR)
    except (OSError, subprocess.CalledProcessError):
        print(MSG_VENV_FAILED, file=sys.stderr)
        return 1
    try:
        install_package(VENV_DIR, REPO_DIR)
    except (OSError, subprocess.CalledProcessError):
        print(MSG_INSTALL_FAILED, file=sys.stderr)
        return 1
    install_shortcut(sys.platform, VENV_DIR, REPO_DIR)
    print(MSG_DONE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
