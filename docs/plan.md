# Plan — ExitMap v1

Describe cómo se construye lo definido en `spec.md`, cumpliendo `constitution.md`.

**Contexto de uso:** uso propio, repositorio público en GitHub con licencia MIT. No se
empaqueta ni se distribuye: se ejecuta desde el código, directamente o mediante un acceso
directo con icono que crea un script. Cada usuario usa su propio registro OAuth en Google y
Microsoft, siguiendo la guía de registro (`docs/guia-registro.md`, enlazada desde el README).

## 1. Stack

| Elemento | Elección | Justificación (constitución 3 y 4) |
|---|---|---|
| Lenguaje | Python ≥ 3.11 | Experiencia del desarrollador; `tomllib`, `StrEnum`, mejoras de `sqlite3`. |
| Interfaz | `tkinter` + `ttk` (stdlib) | Ligera, sin dependencias. Selector de fecha con `Entry` validado (DD/MM/AAAA) para no añadir `tkcalendar`. |
| OAuth 2.0 | Módulo propio con `http.server`, `secrets`, `hashlib`, `urllib` | Flujo *loopback* + PKCE (RFC 8252/7636), idéntico para ambos proveedores (principio 1). |
| API de correo | Gmail REST API y Microsoft Graph vía `urllib.request` + `json` | Sin SDKs; aislado por proveedor. |
| Parseo | `email`, `html.parser` (stdlib) | Cabeceras y extracción de enlaces del cuerpo. |
| Persistencia | `sqlite3` (stdlib) | Transacciones → resultados atómicos (F2-5/6). |
| Credenciales | `keyring` | MIT, mantenimiento activo, muy usado, sin CVE abiertas conocidas. Usa Credential Manager (Windows) y Secret Service/KWallet (Linux). |
| Cifrado (sin llavero) | `cryptography` (Fernet) + `hashlib.scrypt` | Apache-2.0/BSD, PyCA, estándar de facto. La stdlib no trae cifrado simétrico. |
| Tests | `pytest`, `pytest-cov` (solo desarrollo) | MIT, estándar. |
| Instalación | `venv` + `pip` (stdlib) con `pyproject.toml` | Sin herramientas extra. Versiones fijadas. |

Dependencias de ejecución: **2** (`keyring`, `cryptography`). Antes de añadirlas se
re-comprueba estado de mantenimiento, licencia y avisos de seguridad (PyPI / GitHub Advisory)
y se comunica al desarrollador.

## 2. Arquitectura

Capas con dependencias hacia dentro: la interfaz usa servicios de aplicación; estos usan el
dominio y los puertos (`MailProvider`, `CredentialStore`, `Repository`).

```
exitmap/
  __main__.py            # arranque: datos, credenciales, ventana principal
  config.py              # carpeta de datos por SO, ajustes (modo sesión)
  errors.py              # excepciones con mensaje para el usuario (qué falla + solución)
  logging_setup.py       # logging con filtro que elimina asuntos, cuerpos y tokens
  domain/
    models.py            # Account, Service, Evidence, State, RelationType, LinkSource…
    detection.py         # reglas: suscripción / cuenta registrada / acceso concedido
    domains.py           # dominio remitente → dominio registrable
    links.py             # orden catálogo → correo → web principal (F4-3)
    catalog.py           # carga data/catalog.json
  providers/
    base.py              # Protocol MailProvider
    http.py              # GET/POST JSON con urllib, reintentos ante 429, error "sin conexión"
    oauth.py             # flujo loopback + PKCE, refresco de tokens
    gmail.py             # Gmail API
    outlook.py           # Microsoft Graph
  storage/
    db.py                # esquema SQLite y repositorio
    credentials.py       # KeyringStore, EncryptedFileStore, MemoryStore + política
  app/
    accounts.py          # conectar / quitar cuenta (F1, F9)
    analysis.py          # orquestador en hilo, progreso, cancelación, fusión (F2, F8)
    unsubscribe.py       # baja automática / web / mailto (F5)
    services.py          # lista, filtros, orden, estados, avisos (F3, F4, F6, F7)
  ui/
    main_window.py, analysis_dialog.py, service_detail.py, dialogs.py
    presenters.py        # lógica de vista sin widgets (testeable)
    strings_es.py        # todos los textos en español en un solo módulo
data/catalog.json, data/rules.json
assets/exitmap.png, assets/exitmap.ico
scripts/install.py       # crea .venv, instala, crea acceso directo
tests/unit, tests/integration, tests/fixtures
```

**Concurrencia:** el análisis corre en un `threading.Thread`; progreso por `queue.Queue`
leída desde Tk con `after()`. Cancelación con `threading.Event`. Un único análisis a la vez:
`AnalysisService` tiene un cerrojo y la UI deshabilita "Analizar" (F2-9).

**Interfaz `MailProvider`** (una implementación por proveedor, probadas por separado):
`authorize()`, `account_email()`, `list_message_ids(period, folders)`,
`get_headers(id)`, `get_body(id)`, `revoke()` (puede lanzar `RevokeNotSupported`).
Los servicios de aplicación no crean proveedores concretos: reciben una fábrica
`(proveedor, registro, tokens) → MailProvider` (`app/accounts.py`, `build_provider`; en los
tests, una fábrica falsa). Gmail y Outlook exponen además la propiedad `tokens` para que la
app guarde los tokens tras autorizar; el Protocol `MailProvider` no cambia.

**Abrir enlaces fuera de la app:** interfaz `Opener` (`open_url`, `open_mail`) en
`app/unsubscribe.py`, usada también por `app/services.py` (F6). `SystemOpener` usa
`webbrowser` para las webs y, para `mailto:`, `os.startfile` en Windows y `xdg-open` en
Linux (en otros sistemas, el navegador). En los tests se inyecta un abridor falso.

**Arranque con icono:** `scripts/install.py` crea `.venv`, instala el paquete y crea:
Linux → `~/.local/share/applications/exitmap.desktop` (+ copia en el escritorio);
Windows → `.lnk` en Escritorio y menú Inicio mediante PowerShell (`WScript.Shell`), lanzando
`pythonw.exe -m exitmap` para que no aparezca consola. También se puede ejecutar
`python -m exitmap`.

**Carpeta de datos:** Linux `$XDG_DATA_HOME/exitmap` (o `~/.local/share/exitmap`), Windows
`%APPDATA%\ExitMap`. Función propia en `config.py` (sin `platformdirs`). Permisos 0600/0700
en Linux.

## 3. Modelo de datos (SQLite)

```
accounts(id, provider, email, client_registration_ref, last_complete_analysis_at, created_at)
services(id, account_id → accounts, domain, name,
         is_registered, is_subscription, is_access,          -- tipos de relación
         first_email_at, last_email_at, email_count,
         state, state_changed_at, has_alert,
         manage_url, manage_url_source,                      -- catalog|email|homepage
         unsubscribe_method, unsubscribe_target,             -- one_click|web|mailto
         UNIQUE(account_id, domain))
evidence(id, service_id → services, provider_message_id, subject, sent_at, relation_type)
settings(key, value)                                         -- session_mode, etc.
```

- `state` ∈ {pending, keep, unsubscribed, access_revoked, account_deleted, dismissed}
  (*pendiente*, *conservar*, *baja realizada*, *acceso revocado*, *cuenta eliminada*,
  *descartado*; los textos en español que ve el usuario están en `ui/strings_es.py`).
- Borrar una cuenta = `DELETE` en cascada + borrado de sus credenciales (F9-2).
- Los asuntos de la evidencia se guardan en local (permitido); nunca van a los logs.

**Fusión al terminar un análisis completo** (una sola transacción):
- Análisis "todos los correos": recalcula estadísticas y evidencia; **conserva `state`**.
- Servicios existentes que no aparecen en un re-análisis completo: se mantienen sin cambios.
- "Solo nuevos": consulta desde `last_complete_analysis_at`; suma recuentos y añade evidencia.
- Aviso F8-4: `state = unsubscribed` y correo nuevo con fecha > `state_changed_at` → `has_alert = 1`.
  Abrir la ficha pone `has_alert = 0` (F8-5).
- Cancelación o interrupción: no se hace `COMMIT` → quedan los datos del último análisis completo.
- Marca de interrupción (F2-6): al empezar un análisis se guarda `analysis_in_progress` en
  `settings` y se borra al terminar o cancelar. Si sigue presente al arrancar la app, se avisa
  al usuario de que el análisis se interrumpió y se borra la marca.

## 4. Integraciones externas

**Detección de "sin conexión":** no hay comprobación aparte. Un error de red en cualquier
petición (`providers/http.py`) lanza la excepción "sin conexión"; la interfaz pasa a modo sin
conexión hasta el siguiente intento que tenga éxito. En ese modo no se deshabilita nada (si
no, no habría ningún intento posible): la ventana principal muestra un aviso fijo que indica
que analizar, la baja automática y la retirada del permiso al quitar una cuenta necesitan
conexión (spec §5). Si se intentan y fallan, se aplica lo de siempre: la baja abre la web
(F5-3) y quitar la cuenta borra los datos locales e indica dónde retirar el permiso (F9-4).

**OAuth (ambos):** navegador del sistema → redirección a un servidor local que escucha en
`127.0.0.1:<puerto aleatorio>`. La `redirect_uri` usa `http://127.0.0.1:<puerto>` en Google y
`http://localhost:<puerto>` en Microsoft (Microsoft compara el host con el registrado,
`http://localhost`, e ignora el puerto). PKCE S256, parámetro `state` verificado, servidor
local de una sola petición con tiempo límite.
Refresco automático; si el refresco falla → error "permiso caducado o retirado" con opción de
reconectar (caso límite de la spec).

**Registro y conexión (`app/accounts.py`, F1):**
- Un registro por proveedor (no por cuenta), guardado en el almacén de credenciales con la
  clave `registration:<proveedor>` y reutilizado por las demás cuentas de ese proveedor.
  `accounts.client_registration_ref` guarda esa clave.
- Antes de autorizar se quitan los espacios y se comprueba que no faltan campos (Google:
  client ID y secret; Microsoft: client ID) → `InvalidRegistrationError`. Sin registro
  guardado ni introducido → `RegistrationMissingError` (F1-2).
- El registro y los tokens solo se guardan si la autorización tiene éxito. Tokens con la
  clave `tokens:<proveedor>:<email>` (JSON con `access_token`, `refresh_token`,
  `expires_at` e `id_token`).
- Cuenta ya conectada (F1-7): no se añade a la BD, pero sus tokens se sustituyen por los
  nuevos; así se reconecta una cuenta.

**Quitar cuenta (`app/accounts.py`, F9):** el resumen de la confirmación da la cuenta y su
número de servicios (F9-1). Al confirmar: 1) retirar el permiso con los tokens guardados;
2) borrar los tokens del almacén; 3) `DELETE` de la cuenta (cascada). Si no se puede retirar
el permiso (Outlook, sin conexión, permiso ya caducado, error HTTP o sin registro/tokens,
p. ej. en modo sesión tras reabrir), los datos locales se borran igualmente y el resultado
incluye la página donde retirarlo a mano (F9-4). Si falla el llavero al borrar los tokens,
se lanza `KeyringUnavailableError` y la cuenta no se borra, para poder reintentarlo. El
registro del proveedor se conserva.

**Gmail**
- Ámbito: `gmail.readonly` (mínimo que permite leer el cuerpo para extraer enlaces; principio 7).
  `gmail.metadata` no basta para F4-3 paso 2.
- Registro del usuario: proyecto en Google Cloud, cliente "Escritorio", pantalla de
  consentimiento **en producción sin verificar** (evita la caducidad de 7 días del modo prueba).
- Listado: `users.messages.list` con `q=after:/before:` y `includeSpamTrash` según carpetas
  elegidas (filtrando etiquetas SPAM/TRASH con `-in:spam`/`-in:trash` en `q`). Se analiza todo
  el buzón (incluidos archivados) excepto Enviados y Borradores (`-in:sent -in:drafts`), y
  Spam/Papelera solo si se eligen. Primero se listan IDs (total exacto para el
  progreso), después `messages.get?format=metadata` con `From, Subject, Date,
  List-Unsubscribe, List-Unsubscribe-Post`. Cuerpo (`format=full`) solo para los correos de
  evidencia de registro/acceso sin entrada en catálogo.
- Revocación: `POST https://oauth2.googleapis.com/revoke`. Retirada manual (F9-4):
  `https://myaccount.google.com/permissions`.

**Microsoft (Outlook/Hotmail)**
- Ámbitos: `Mail.Read`, `offline_access`, `openid`, `email`. Autoridad `common`.
- Registro del usuario: app en Azure, plataforma "cliente público/móvil y escritorio",
  redirección `http://localhost`. Sin secreto.
- Listado: `/me/messages` (todas las carpetas) con `$filter=receivedDateTime` y `$select` de
  `parentFolderId` y cabeceras (`internetMessageHeaders`). Mismo criterio que Gmail: se excluyen
  los mensajes de `sentitems` y `drafts`, y los de `junkemail` y `deleteditems` salvo que el
  usuario los incluya (los ID de esas carpetas se obtienen con `/me/mailFolders/{nombre}`).
  El total exacto es el número de ID tras recorrer todas las páginas, como en Gmail.
- Revocación: **Microsoft no ofrece un endpoint para que la app revoque su propio permiso en
  cuentas personales** → se aplica F9-4 (F9-4 de la spec). Retirada manual:
  `https://account.live.com/consent/Manage`.

**Baja (F5)** a partir de `List-Unsubscribe`:
- `https` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` → `POST` (RFC 8058) con el
  cuerpo `List-Unsubscribe=One-Click`; éxito = 2xx. Se envía con `HttpClient.post_form`, que
  devuelve el estado sin leer la respuesta como JSON (estos enlaces responden con HTML).
- Solo `https` → abrir en navegador (`webbrowser`).
- Solo `mailto:` → abrir el programa de correo con asunto/cuerpo preparados
  (`os.startfile` en Windows, `xdg-open` en Linux). La app no envía nada. Si el enlace no
  trae asunto, se añade `subject=unsubscribe`.
- Fallo del POST → mensaje con el motivo y apertura del mismo enlace web (F5-3). Motivo:
  `OfflineError` sin conexión; `UnsubscribeFailedError` ante cualquier otro fallo.

**Catálogo:** `data/catalog.json` en el repositorio, indexado por dominio
(`name, manage_url, unsubscribe_url`). Se actualiza con `git pull`. Sin conexiones a servidores
propios (principio 6).

## 5. Detección (reglas)

- **Dominio del servicio:** dominio del `From` reducido a dominio registrable (últimas dos
  etiquetas, o tres si la penúltima está en una lista corta incluida de sufijos compuestos:
  `co.uk`, `com.es`, `com.mx`, `com.br`, `com.au`, `co.jp`…).
- **Suscripción comercial:** el correo tiene `List-Unsubscribe`.
- **Cuenta registrada:** el asunto coincide con patrones ES/EN de `data/rules.json`
  (bienvenida, verifica/confirma tu cuenta, restablecer contraseña…).
- **Acceso/permiso concedido:** patrones de nueva app conectada, autorización, API key,
  nuevo inicio de sesión, integración…
- Solo los correos que cumplen alguna regla crean servicio y evidencia → el correo personal
  no genera servicios.
- **Nombre:** nombre visible más frecuente del remitente; si no hay, catálogo o dominio.

## 6. Estrategia de tests

- `pytest` + `pytest-cov`, `--cov-fail-under=75` (principio 2).
- **Unitarios** (uno o más por módulo): reglas, dominios, enlaces, catálogo, repositorio,
  política de credenciales, PKCE/state, parseo de respuestas Gmail/Graph (JSON grabado
  sintético), métodos de baja, presentadores (filtros, orden F3-2, avisos).
- **Integración** (al menos uno por funcionalidad F1-F10):
  - `FakeMailProvider` + SQLite temporal + servicios de aplicación (análisis completo,
    cancelación, interrupción, re-análisis, avisos, quitar cuenta).
  - `gmail.py` y `outlook.py` contra un servidor HTTP local que imita sus endpoints (sin red real).
  - Baja one-click contra servidor HTTP local.
  - **Buzón de prueba** `tests/fixtures/mailbox.json` con casos conocidos → F2-7.
- **Privacidad:** test que captura los logs de un análisis y comprueba que no contienen
  asuntos, cuerpos ni tokens.
- **UI:** widgets finos sin lógica; prueba de humo de Tk (se omite si no hay pantalla).
- Correos de prueba sintéticos: nunca correos reales en el repositorio.

## 7. Seguridad y privacidad

- Conexiones externas: solo proveedor (OAuth + API), URL de baja confirmadas por el usuario y
  el navegador abierto por el usuario. Sin telemetría.
- **Credenciales (tokens):**
  1. Modo sesión activado (ajuste) → `MemoryStore`: nada en disco; al cerrar se pierden.
  2. Llavero disponible → `KeyringStore`.
  3. Sin llavero → el usuario elige contraseña maestra (`EncryptedFileStore`: scrypt + Fernet,
     sal aleatoria; se pide al abrir la app) o modo sesión. Elegir modo sesión activa el
     ajuste (F10-2).
  - Orden de la política (`choose_store`): modo sesión → llavero → fichero cifrado. Si hay
    llavero, se usa aunque exista un fichero cifrado. Sin llavero: si existe el fichero se
    pide la contraseña; si no, el usuario elige.
  - Ajuste `session_mode` en `settings` (`"1"`/`"0"`, desactivado por defecto). Al activarlo
    se borran las credenciales guardadas en el llavero o en el fichero cifrado (F10-6).
  - Fichero cifrado: `credentials.enc` en la carpeta de datos; JSON con la sal (16 bytes) y
    un único bloque Fernet con todas las credenciales. Se reescribe entero en cada cambio
    (fichero temporal + renombrado atómico) y tiene permisos 0600 en Linux. scrypt con
    `n=2^15, r=8, p=1` (valores recomendados para inicio de sesión interactivo).
  - Un fichero dañado no se distingue de una contraseña incorrecta: mismo error y misma
    salida (restablecer, F10-5).
  - Un fallo del llavero en uso (bloqueado, acceso denegado) lanza `KeyringUnavailableError`
    con mensaje comprensible (principio 5).
  - Elección sin llavero (F10-2): `store_from_choice` crea el fichero cifrado con la
    contraseña elegida o, si se elige el modo sesión, activa el ajuste y devuelve un
    `MemoryStore`. Mientras el usuario no ha elegido, `AccountService.store` es `None` y no
    se puede conectar ninguna cuenta.
- Datos de registro OAuth (client ID y, en Google, client secret de escritorio, que Google no
  considera confidencial) → en el mismo almacén de credenciales (claves en §4 "Registro y
  conexión"). En modo sesión también se pierden al cerrar la app.
- Logs: sin contenido de correos ni credenciales (filtro + test). Errores con mensaje
  personalizado (`errors.py`, principio 5).
- Mínimos privilegios: `gmail.readonly` y `Mail.Read`; nada de envío.
- Confirmación explícita antes de dar de baja y de quitar una cuenta (principio 8).
- El OAuth propio se limita al flujo estándar y tiene tests específicos (state, PKCE,
  puerto loopback, tiempo límite).

## 8. Riesgos técnicos

| Riesgo | Mitigación |
|---|---|
| Cuotas de Gmail: buzones grandes tardan minutos | Progreso visible, solo cabeceras, cuerpo solo cuando hace falta; reintento con espera ante 429. |
| `internetMessageHeaders` en listados de Graph puede no estar disponible | Prueba temprana; si falla, petición por mensaje con `$select`. |
| Heurísticas imprecisas (falsos positivos/negativos) | Evidencia visible + estado *descartado*; reglas en JSON fácil de ampliar. |
| Pantalla "app no verificada" de Google asusta al usuario | Explicado en la guía de registro (`docs/guia-registro.md`, enlazada desde el README). |
| Linux sin `python3-tk` o sin Secret Service | Mensaje claro al arrancar; política de credenciales sin llavero. |
| OAuth escrito a mano | Flujo estándar mínimo, tests dedicados. |
| Dominio registrable aproximado | Lista de sufijos ampliable; agrupación real fuera de alcance. |
| Acceso directo en Windows vía PowerShell | Si falla, el script indica cómo arrancar con `python -m exitmap`. |

## 9. Trazabilidad spec → plan

| Spec | Parte del plan |
|---|---|
| F1 Conectar cuentas | `providers/oauth.py`, `gmail.py`, `outlook.py`, `app/accounts.py`, `storage/credentials.py`; §4 |
| F2 Analizar | `app/analysis.py` (hilo, progreso, cancelación, transacción), `domain/detection.py`, `domains.py`; §3, §5 |
| F3 Lista y filtros | `app/services.py` (búsqueda sin distinguir mayúsculas en nombre y dominio; un valor como máximo por filtro: cuenta, tipo, estado), `ui/presenters.py`, `ui/main_window.py` |
| F4 Ficha | `ui/service_detail.py`, `domain/links.py`, `catalog.py`; tabla `evidence` |
| F5 Baja | `app/unsubscribe.py`; §4 Baja |
| F6 Eliminar/revocar (abrir web) | `app/services.py` + `webbrowser`; `manage_url` |
| F7 Estados | `services.state`, `state_changed_at`; `app/services.py` |
| F8 Re-análisis y avisos | Fusión en §3; `has_alert` |
| F9 Quitar cuenta | `app/accounts.py`, borrado en cascada, `MailProvider.revoke()` |
| F10 Credenciales | `storage/credentials.py`; §7 |
| Casos límite (sin conexión, permiso caducado, error) | `errors.py`, refresco OAuth §4, aviso de sin conexión en la UI §4 |
| Persistencia entre sesiones | SQLite en carpeta de datos §2 |
| Interfaz en español | `ui/strings_es.py` |
