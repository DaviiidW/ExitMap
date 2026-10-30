# Tareas — ExitMap v1

Cada tarea deja el proyecto funcionando: `pytest` en verde y cobertura ≥ 75 %
(`pytest --cov=exitmap --cov-fail-under=75`). Los tests van en la misma tarea que el código.

## Fase 0 — Preparación

- [x] T001 — Esqueleto del proyecto
  - Qué: `pyproject.toml` (Python ≥ 3.11; `pytest` y `pytest-cov` como dependencias de
    desarrollo; umbral de cobertura 75 %), paquete `exitmap/` vacío con `__main__.py`,
    `tests/unit`, `tests/integration`, `tests/fixtures`, `LICENSE` (MIT), `.gitignore`.
  - Referencia: plan §1, §2, §6.
  - Hecho cuando: `pip install -e .[dev]` funciona en un `venv` y `pytest` pasa con un test
    de humo que importa `exitmap`.

## Fase 1 — Base

- [x] T002 — Carpeta de datos
  - Qué: `config.py` con la ruta de datos por SO (`$XDG_DATA_HOME/exitmap`,
    `~/.local/share/exitmap`, `%APPDATA%\ExitMap`), creación y permisos 0700 en Linux.
  - Referencia: plan §2 "Carpeta de datos".
  - Hecho cuando: tests unitarios para Linux/Windows (entorno simulado) y de integración que
    crea la carpeta en un directorio temporal y comprueba permisos.

- [x] T003 — Errores comprensibles
  - Qué: `errors.py` (jerarquía de excepciones con "qué falla" + "solución probable") y
    `ui/strings_es.py` con los textos de error.
  - Referencia: constitución 5; spec §5 "Cualquier error"; plan §7.
  - Hecho cuando: tests que comprueban que cada excepción da un mensaje en español no vacío y
    sin datos sensibles.

- [x] T004 — Logging sin datos sensibles
  - Qué: `logging_setup.py` con fichero de log en la carpeta de datos y filtro que elimina
    asuntos, cuerpos, direcciones y tokens.
  - Referencia: constitución 6; plan §7.
  - Hecho cuando: test que registra mensajes con asunto/token simulados y comprueba que el
    fichero no los contiene.

- [x] T005 — Modelos de dominio
  - Qué: `domain/models.py`: `State`, `RelationType`, `LinkSource`, `UnsubscribeMethod`,
    `Provider` y dataclasses `Account`, `Service`, `Evidence`.
  - Referencia: plan §2, §3; spec F7 (tabla de estados).
  - Hecho cuando: tests unitarios de valores y valores por defecto (estado *pendiente*).

- [x] T006 — Esquema SQLite y cuentas
  - Qué: `storage/db.py`: creación del esquema (`accounts`, `services`, `evidence`,
    `settings`), claves foráneas en cascada, alta/listado/borrado de cuentas, `UNIQUE` por
    proveedor+email.
  - Referencia: plan §3.
  - Hecho cuando: tests de integración con BD temporal: crear, listar, no duplicar, borrar en
    cascada.

- [x] T007 — Repositorio de servicios, evidencia y ajustes
  - Qué: leer/guardar servicios y evidencia, cambiar estado (con `state_changed_at`), activar
    y quitar `has_alert`, leer/escribir `settings`.
  - Referencia: plan §3; spec F7-1, F7-2.
  - Hecho cuando: tests: un estado cambiado persiste tras reabrir la BD; el aviso se activa y
    se quita.

## Fase 2 — Detección (lógica pura)

- [x] T008 — Dominio registrable
  - Qué: `domain/domains.py` con lista corta de sufijos compuestos.
  - Referencia: plan §5; spec §3 "Servicio".
  - Hecho cuando: tests: `news.amazon.es`→`amazon.es`, `mail.bbc.co.uk`→`bbc.co.uk`,
    mayúsculas, direcciones con nombre visible.

- [x] T009 — Reglas de detección
  - Qué: `data/rules.json` (patrones ES/EN) y `domain/detection.py`: cabeceras → tipos de
    relación; correo sin regla → ninguno.
  - Referencia: plan §5.
  - Hecho cuando: tests por tipo (registro, suscripción por `List-Unsubscribe`, acceso),
    combinación de tipos y correo personal sin tipo.

- [x] T010 — Catálogo
  - Qué: `data/catalog.json` inicial con Google, Microsoft, Amazon, Netflix, Spotify,
    Facebook, Instagram, LinkedIn, X y PayPal, y `domain/catalog.py` (búsqueda por dominio;
    fichero ausente o mal formado → error comprensible).
  - Referencia: plan §4 "Catálogo".
  - Hecho cuando: tests de carga, búsqueda, dominio inexistente y JSON inválido; el
    desarrollador verifica a mano que los enlaces del catálogo inicial funcionan.

- [x] T011 — Lectura de `List-Unsubscribe`
  - Qué: función que, a partir de `List-Unsubscribe` y `List-Unsubscribe-Post`, devuelve el
    método (`one_click`, `web`, `mailto`) y el destino.
  - Referencia: plan §4 "Baja"; spec F5.
  - Hecho cuando: tests con cabecera solo https, https + Post, solo mailto, ambos, ausente y
    mal formada.

- [x] T012 — Enlace de gestión
  - Qué: `domain/links.py`: extracción de enlaces del HTML con `html.parser` y orden
    catálogo → correo → web principal, devolviendo URL y origen.
  - Referencia: spec F4-3, F4-4; plan §4, §5.
  - Hecho cuando: tests para cada uno de los tres orígenes y para HTML sin enlaces.

## Fase 3 — Análisis con proveedor falso

- [ ] T013 — Puerto `MailProvider` y buzón de prueba
  - Qué: `providers/base.py` (Protocol, `Period`, `Folders`, `RevokeNotSupported`),
    `FakeMailProvider` en `tests/` y `tests/fixtures/mailbox.json` sintético con casos
    conocidos.
  - Referencia: plan §2 "Interfaz MailProvider", §6.
  - Hecho cuando: test que comprueba que el falso cumple el Protocol y filtra por periodo y
    carpetas.

- [ ] T014 — Agregación de un análisis
  - Qué: `app/analysis.py`: de los mensajes a servicios en memoria (tipos, fechas,
    recuento, nombre, evidencia, enlace de gestión y método de baja).
  - Referencia: spec F2-7, F3-1, F4-1..3; plan §5.
  - Hecho cuando: test de integración con el buzón de prueba: cada servicio esperado aparece
    con sus tipos (F2-7); mismo servicio en dos cuentas = dos entradas (F3-1).

- [ ] T015 — Fusión y guardado
  - Qué: guardado en una transacción; modo "todos" y "solo nuevos"; conservar estados;
    mantener servicios no re-detectados; activar aviso tras *baja realizada*; actualizar
    `last_complete_analysis_at`.
  - Referencia: plan §3 "Fusión"; spec F2-8, F7-1, F8-3, F8-4, F8-6.
  - Hecho cuando: tests de integración para cada regla de fusión y persistencia tras reabrir
    la BD.

- [ ] T016 — Ejecución en segundo plano
  - Qué: hilo con progreso (`queue.Queue`), cancelación (`threading.Event`), cerrojo de un
    único análisis, marca `analysis_in_progress` en `settings`, sin `COMMIT` si se cancela o
    falla.
  - Referencia: plan §2 "Concurrencia", §3 "Marca de interrupción"; spec F2-4, F2-5, F2-6,
    F2-9.
  - Hecho cuando: tests: progreso "n de total"; cancelar conserva el último análisis
    completo; error de red a mitad igual; segundo análisis rechazado; marca presente tras
    interrupción simulada.

## Fase 4 — Credenciales

- [ ] T017 — Verificar y añadir dependencias
  - Qué: comprobar mantenimiento, licencia y avisos de seguridad de `keyring` y
    `cryptography`; comunicarlo al desarrollador; fijar versiones en `pyproject.toml`.
  - Referencia: constitución 3; plan §1.
  - Hecho cuando: el desarrollador recibe el informe y lo aprueba; `pip install -e .[dev]` y
    `pytest` pasan.

- [ ] T018 — Almacén en memoria y en llavero
  - Qué: `storage/credentials.py`: interfaz `CredentialStore`, `MemoryStore`, `KeyringStore`
    y detección de llavero disponible.
  - Referencia: plan §7; spec F10-1.
  - Hecho cuando: tests con backend de `keyring` falso: guardar, leer, borrar, llavero
    ausente detectado.

- [ ] T019 — Almacén cifrado con contraseña
  - Qué: `EncryptedFileStore` (scrypt + Fernet, sal aleatoria), contraseña incorrecta,
    restablecer.
  - Referencia: plan §7; spec F10-3, F10-4, F10-5.
  - Hecho cuando: tests: ida y vuelta, el fichero no contiene el token en claro, contraseña
    incorrecta da error comprensible, restablecer borra credenciales y conserva la BD.

- [ ] T020 — Política de credenciales
  - Qué: elegir almacén según modo sesión (ajuste), llavero disponible o necesidad de elegir
    contraseña/sesión.
  - Referencia: plan §7; spec F10-1, F10-2, F10-6, F10-7.
  - Hecho cuando: tests de las cuatro combinaciones; en modo sesión no se escribe nada en
    disco y los resultados de la BD se conservan.

## Fase 5 — OAuth y proveedores

- [ ] T021 — Cliente HTTP mínimo
  - Qué: `providers/http.py`: GET/POST JSON con `urllib`, reintento con espera ante 429,
    errores de red → excepción "sin conexión".
  - Referencia: plan §2, §4 "Detección de sin conexión", §8 (cuotas).
  - Hecho cuando: tests contra servidor HTTP local: 200, 429 + reintento, 500, sin red.

- [ ] T022 — OAuth: PKCE, URL, código y refresco
  - Qué: `providers/oauth.py`: generación de verificador/desafío S256 y `state`, URL de
    autorización, intercambio de código y refresco de token.
  - Referencia: plan §4 "OAuth".
  - Hecho cuando: tests unitarios de PKCE/URL y de integración contra servidor de tokens
    local (intercambio, refresco, refresco rechazado → error "permiso caducado").

- [ ] T023 — OAuth: receptor loopback
  - Qué: servidor local de una sola petición en puerto aleatorio, verificación de `state`,
    tiempo límite, denegación del usuario.
  - Referencia: plan §4, §7; spec F1-6.
  - Hecho cuando: tests: código recibido, `state` erróneo rechazado, `error=access_denied` →
    error comprensible, tiempo límite.

- [ ] T024 — Gmail: listado
  - Qué: `providers/gmail.py`: listado paginado de IDs con `after:/before:` e inclusión de
    Spam/Papelera según elección; total exacto.
  - Referencia: plan §4 "Gmail"; spec F2-1, F2-3.
  - Hecho cuando: tests contra servidor local que imita Gmail: paginación, periodo, carpetas.

- [ ] T025 — Gmail: cabeceras, cuerpo, cuenta y revocación
  - Qué: `messages.get` metadata/full, `getProfile`, `revoke`; ámbito `gmail.readonly`.
  - Referencia: plan §4; spec F1-4, F9-3.
  - Hecho cuando: tests contra servidor local; test que comprueba que el único ámbito pedido
    es `gmail.readonly`.

- [ ] T026 — Outlook: listado
  - Qué: `providers/outlook.py`: carpetas (bandeja + `junkemail`/`deleteditems` si se
    eligen), `$filter` por fecha, paginación, `$count`.
  - Referencia: plan §4 "Microsoft"; spec F2-1, F2-3.
  - Hecho cuando: tests contra servidor local que imita Graph.

- [ ] T027 — Outlook: cabeceras, cuerpo, cuenta y revocación
  - Qué: `internetMessageHeaders`, cuerpo, email desde `id_token`, `revoke()` lanza
    `RevokeNotSupported`; ámbitos `Mail.Read offline_access openid email`.
  - Referencia: plan §4; spec F1-4, F9-4.
  - Hecho cuando: tests contra servidor local; test de ámbitos.

- [ ] T028 — Comprobación temprana con cuentas reales (manual)
  - Qué: con el registro propio del desarrollador, autorizar y listar unas cabeceras en una
    cuenta Gmail y otra Outlook desde una sesión interactiva de Python.
  - Referencia: plan §8 (riesgo `internetMessageHeaders`).
  - Hecho cuando: el desarrollador confirma que ambos proveedores devuelven cabeceras; si
    Graph no las da en el listado, se aplica la mitigación del plan antes de seguir.
  - Nota: requiere que el desarrollador tenga ya sus registros en Google y Microsoft; si no
    los tiene, se adelanta T044.

## Fase 6 — Servicios de aplicación

- [ ] T029 — Conectar cuenta
  - Qué: `app/accounts.py`: exigir datos de registro, autorizar, obtener email, no duplicar,
    guardar credenciales según la política.
  - Referencia: spec F1-2, F1-3, F1-5, F1-6, F1-7, F10-1, F10-2.
  - Hecho cuando: tests de integración con proveedor falso para cada criterio citado.

- [ ] T030 — Quitar cuenta
  - Qué: resumen de lo que se borrará, borrado en cascada y de credenciales, revocación
    (Gmail) o instrucciones (Outlook / fallo de red).
  - Referencia: spec F9-1..4.
  - Hecho cuando: tests de integración: datos borrados tras reabrir la BD; revocación
    llamada en Gmail; instrucciones en Outlook y sin red.

- [ ] T031 — Lista, ficha y estados
  - Qué: `app/services.py`: búsqueda, filtros combinados, orden (aviso → pendiente → resto,
    por nombre), detalle con evidencia (quita el aviso), cambio de estado.
  - Referencia: spec F3-2..4, F4-1, F4-2, F7-2, F8-5.
  - Hecho cuando: tests de integración con BD poblada para cada criterio citado.

- [ ] T032 — Darse de baja
  - Qué: `app/unsubscribe.py`: POST one-click (éxito → *baja realizada*), fallo → motivo +
    abrir web, web, `mailto:` preparado; apertura con `webbrowser` / `os.startfile` /
    `xdg-open` inyectable.
  - Referencia: spec F5-2..5; plan §4 "Baja".
  - Hecho cuando: tests contra servidor local (2xx, 4xx/5xx, sin red) y con abridor falso.

- [ ] T033 — Abrir gestión de cuenta
  - Qué: abrir `manage_url` sin cambiar el estado.
  - Referencia: spec F6-1, F6-2.
  - Hecho cuando: test con abridor falso: URL abierta, estado sin cambios.

## Fase 7 — Interfaz

- [ ] T034 — Presentadores
  - Qué: `ui/presenters.py`: estado de la lista (mensajes vacíos), validación de fechas
    DD/MM/AAAA, opciones por defecto del análisis, texto de confirmación de baja, de quitar
    cuenta y de re-análisis.
  - Referencia: spec F2-1, F2-2, F2-3, F2-10, F3-5, F5-1, F8-1, F8-2, F9-1.
  - Hecho cuando: tests unitarios de cada presentador.

- [ ] T035 — Ventana principal
  - Qué: `ui/main_window.py`: panel de cuentas, buscador, filtros, lista (`ttk.Treeview`) y
    aviso destacado.
  - Referencia: spec F3; plan §2.
  - Hecho cuando: prueba de humo de Tk (se omite sin pantalla) y comprobación manual con una
    BD de ejemplo.

- [ ] T036 — Conectar cuenta (interfaz)
  - Qué: elegir proveedor, formulario de datos de registro con enlace a
    `docs/guia-registro.md`, mensajes de error, lista de cuentas.
  - Referencia: spec F1-1, F1-2, F1-6, F1-7.
  - Hecho cuando: prueba de humo y comprobación manual con proveedor falso.

- [ ] T037 — Diálogo de análisis
  - Qué: periodo (por defecto "Buzón entero"), rango validado, Spam/Papelera desactivados,
    modo de re-análisis + aviso de estados, barra de progreso, cancelar, resultado vacío.
  - Referencia: spec F2-1..5, F2-9, F2-10, F8-1, F8-2.
  - Hecho cuando: prueba de humo y comprobación manual con proveedor falso lento.

- [ ] T038 — Ficha del servicio
  - Qué: `ui/service_detail.py`: datos, evidencia, origen del enlace, botones de baja,
    eliminar cuenta y revocar acceso con confirmación, selector de estado.
  - Referencia: spec F4, F5-1, F5-6, F6, F7.
  - Hecho cuando: prueba de humo; cancelar la confirmación no ejecuta nada (test con
    abridor falso).

- [ ] T039 — Quitar cuenta (interfaz)
  - Qué: confirmación con resumen y mensaje final (incluidas las instrucciones de
    Outlook).
  - Referencia: spec F9-1, F9-4.
  - Hecho cuando: prueba de humo y comprobación manual.

- [ ] T040 — Credenciales y ajustes (interfaz)
  - Qué: elegir contraseña o modo sesión sin llavero, pedir contraseña al abrir, reintento,
    restablecer, ajuste de modo sesión.
  - Referencia: spec F10-2..7.
  - Hecho cuando: prueba de humo y comprobación manual con llavero simulado ausente.

- [ ] T041 — Sin conexión y permiso caducado
  - Qué: modo "sin conexión" (deshabilita analizar, baja automática y revocación) y oferta
    de reconectar cuando falla el refresco.
  - Referencia: spec §5; plan §4 "Detección de sin conexión".
  - Hecho cuando: tests de presentador y comprobación manual desconectando la red.

- [ ] T042 — Arranque completo
  - Qué: `__main__.py`: carpeta de datos, logging, política de credenciales, aviso de
    análisis interrumpido, ventana principal; mensaje claro si falta `tkinter`.
  - Referencia: spec F2-6, F2-8; plan §2, §3 "Marca de interrupción", §8.
  - Hecho cuando: `python -m exitmap` abre la app y muestra la lista guardada; test de
    integración del aviso de interrupción.

## Fase 8 — Instalación y documentación

- [ ] T043 — Script de instalación y acceso directo
  - Qué: `scripts/install.py` (crea `.venv`, instala, crea `.desktop` en Linux o `.lnk` vía
    PowerShell en Windows con `pythonw.exe`) e icono provisional sencillo en
    `assets/exitmap.png` y `assets/exitmap.ico`.
  - Referencia: plan §2 "Arranque con icono", §8.
  - Hecho cuando: tests unitarios del contenido del `.desktop` y del comando PowerShell;
    comprobación manual en Linux y Windows: el icono abre la app.

- [ ] T044 — Guía de registro en español
  - Qué: `docs/guia-registro.md`: pasos para crear el registro en Google (cliente
    Escritorio, pantalla de consentimiento en producción sin verificar, aviso de "app no
    verificada") y en Microsoft (cliente público, redirección `http://localhost`), y qué datos
    pegar en ExitMap.
  - Referencia: spec §2, F1-2; plan §4, §8.
  - Hecho cuando: el desarrollador sigue la guía en una cuenta nueva y consigue conectar.

- [ ] T045 — README en inglés
  - Qué: `README.md`: qué es ExitMap, requisitos, instalación con `scripts/install.py`,
    resumen del registro OAuth y enlace a `docs/guia-registro.md`, licencia.
  - Referencia: `CLAUDE.md` (README en inglés); plan §2.
  - Hecho cuando: el desarrollador revisa el README y los enlaces funcionan en GitHub.

## Fase 9 — Cierre

- [ ] T046 — Extremo a extremo y privacidad
  - Qué: test de integración del flujo completo con proveedor falso (conectar → analizar →
    filtrar → baja → re-analizar → aviso → quitar cuenta) y comprobación de logs.
  - Referencia: plan §6; constitución 2 y 6.
  - Hecho cuando: el test pasa, los logs no tienen asuntos/cuerpos/tokens y la cobertura
    total es ≥ 75 %.

- [ ] T047 — Prueba manual con cuentas reales
  - Qué: recorrer F1–F10 con una cuenta Gmail y otra Outlook propias, abriendo desde el
    icono.
  - Referencia: plan "Verificación".
  - Hecho cuando: el desarrollador confirma cada funcionalidad; las desviaciones se anotan
    como cambio de spec o de código.
