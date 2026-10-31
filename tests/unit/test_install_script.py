"""Shortcut contents of the installation script (T043; plan §2 "Arranque con icono", §8)."""

from pathlib import Path, PurePosixPath, PureWindowsPath

from install_script import install


def entry_lines(content: str) -> dict[str, str]:
    lines = content.splitlines()
    assert lines[0] == "[Desktop Entry]"
    return dict(line.split("=", 1) for line in lines[1:])


def test_desktop_entry_launches_the_venv_python_without_terminal():
    python = PurePosixPath("/home/ana/ExitMap/.venv/bin/python")
    content = install.desktop_entry(
        python, PurePosixPath("/home/ana/ExitMap"), PurePosixPath("/home/ana/ExitMap/assets/exitmap.png")
    )
    keys = entry_lines(content)
    assert keys["Type"] == "Application"
    assert keys["Name"] == "ExitMap"
    assert keys["Exec"] == '"/home/ana/ExitMap/.venv/bin/python" "-m" "exitmap"'
    assert keys["Path"] == "/home/ana/ExitMap"
    assert keys["Icon"] == "/home/ana/ExitMap/assets/exitmap.png"
    assert keys["Terminal"] == "false"
    assert content.endswith("\n")


def test_desktop_entry_quotes_paths_with_spaces_and_reserved_characters():
    python = PurePosixPath('/home/ana/Spec Driven/$x"`\\/.venv/bin/python')
    keys = entry_lines(install.desktop_entry(python, PurePosixPath("/r"), PurePosixPath("/r/i.png")))
    # Exec rules: \" \` \$ \\ inside quotes, then each backslash doubled (string value).
    assert keys["Exec"].startswith(
        '"/home/ana/Spec Driven/\\\\$x\\\\"\\\\`\\\\\\\\/.venv/bin/python" '
    )


def test_desktop_string_values_escape_backslashes():
    keys = entry_lines(
        install.desktop_entry(PurePosixPath("/p"), PurePosixPath("/a\\b"), PurePosixPath("/i"))
    )
    assert keys["Path"] == "/a\\\\b"


def test_venv_python_per_system():
    venv = Path("v")
    assert install.venv_python(venv, windows=False) == venv / "bin" / "python"
    assert install.venv_python(venv, windows=True) == venv / "Scripts" / "python.exe"
    assert install.venv_python(venv, windows=True, windowed=True) == (
        venv / "Scripts" / "pythonw.exe"
    )


def test_powershell_command_creates_desktop_and_start_menu_shortcuts_with_pythonw():
    pythonw = PureWindowsPath(r"C:\Users\Ana\ExitMap\.venv\Scripts\pythonw.exe")
    repo = PureWindowsPath(r"C:\Users\Ana\ExitMap")
    icon = PureWindowsPath(r"C:\Users\Ana\ExitMap\assets\exitmap.ico")
    command = install.powershell_command(pythonw, repo, icon)
    assert command[:-1] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
    ]
    script = command[-1]
    assert "New-Object -ComObject WScript.Shell" in script
    assert "[Environment]::GetFolderPath('Desktop')" in script
    assert "[Environment]::GetFolderPath('Programs')" in script
    assert "'ExitMap.lnk'" in script
    assert r"$link.TargetPath = 'C:\Users\Ana\ExitMap\.venv\Scripts\pythonw.exe';" in script
    assert "$link.Arguments = '-m exitmap';" in script
    assert r"$link.WorkingDirectory = 'C:\Users\Ana\ExitMap';" in script
    assert r"$link.IconLocation = 'C:\Users\Ana\ExitMap\assets\exitmap.ico,0';" in script
    assert "$link.Save();" in script
    assert "$ErrorActionPreference = 'Stop'" in script


def test_powershell_command_doubles_single_quotes_in_paths():
    pythonw = PureWindowsPath(r"C:\Users\O'Neil\ExitMap\.venv\Scripts\pythonw.exe")
    script = install.powershell_script(pythonw, PureWindowsPath(r"C:\x"), PureWindowsPath(r"C:\i.ico"))
    assert r"$link.TargetPath = 'C:\Users\O''Neil\ExitMap\.venv\Scripts\pythonw.exe';" in script


def test_launch_command_for_manual_start():
    assert install.launch_command(Path("/r/.venv"), windows=False) == (
        f'"{Path("/r/.venv") / "bin" / "python"}" -m exitmap'
    )
