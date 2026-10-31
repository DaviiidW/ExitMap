# ExitMap

ExitMap is a desktop app for Windows and Linux that analyses your email and shows you:

- the services where you have a registered account,
- the services that send you commercial email or newsletters because you are subscribed,
- the services you have granted access or permissions to,

and takes you, from the app, to the place where you can unsubscribe, delete your account or
revoke that access.

It works with **Gmail** and **Outlook/Hotmail** accounts, and you can connect several of
them. The interface is in Spanish.

Everything runs on your computer: credentials, emails and results are processed and stored
only there, without telemetry or servers of its own. ExitMap only asks for read-only access
to your mailbox and never sends email on your behalf.

## Requirements

- Windows or Linux with a desktop session.
- Python 3.11 or later.
- `tkinter`. It comes with Python on Windows; on Linux you may need to install it (for
  example, `sudo apt install python3-tk python3-venv` on Debian/Ubuntu).
- A Google and/or Microsoft account where you can create your own app registration (see
  [OAuth registration](#oauth-registration)).

## Installation

ExitMap is not packaged: it runs from the source code.

```sh
git clone https://github.com/DaviiidW/ExitMap.git
cd ExitMap
python scripts/install.py
```

On Linux, use `python3` if `python` is not available.

The script:

1. creates a virtual environment in `.venv`,
2. installs ExitMap and its dependencies (`keyring` and `cryptography`),
3. creates a shortcut with the ExitMap icon:
   - Linux: in the applications menu and on the desktop
     (`~/.local/share/applications/exitmap.desktop`);
   - Windows: on the desktop and in the Start menu (`ExitMap.lnk`).

Open ExitMap from the shortcut. If the shortcut cannot be created, the script prints the
command to start the app by hand:

```sh
# Linux
.venv/bin/python -m exitmap
# Windows
.venv\Scripts\python.exe -m exitmap
```

To update, run `git pull` and then `python scripts/install.py` again. The data (accounts,
results and states) is kept in `~/.local/share/exitmap` on Linux (or
`$XDG_DATA_HOME/exitmap`) and in `%APPDATA%\ExitMap` on Windows.

## OAuth registration

ExitMap has no servers, so each user connects through **their own app registration** with
Google and/or Microsoft. You only do it once per provider; all the accounts of that provider
then share the same registration.

- **Google (Gmail):** create a Google Cloud project, enable the Gmail API, configure the
  consent screen with the `gmail.readonly` scope and publish it **in production without
  verification**, and create a **Desktop app** OAuth client. ExitMap asks for its
  *Client ID* and *Client secret*. When you connect, Google shows an "unverified app"
  warning: it is expected, since the app is yours.
- **Microsoft (Outlook/Hotmail):** register an app in Microsoft Entra that supports
  **personal Microsoft accounts**, with the **Mobile and desktop applications** platform and
  the redirect URI `http://localhost`. No secret is needed. ExitMap asks for its
  *Application (client) ID*.

The step-by-step guide, in Spanish, is in [`docs/guia-registro.md`](docs/guia-registro.md).
It can also be opened from the registration form in the app.

## License

[MIT](LICENSE)
