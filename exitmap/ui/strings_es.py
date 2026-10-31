"""All user-facing Spanish texts.

Error texts are fixed strings with no placeholders, so they can never carry email
content, addresses or credentials (constitution 5 and 6).
"""

# Error key -> (what failed, most likely solution). An empty solution means none exists.
ERRORS: dict[str, tuple[str, str]] = {
    "unexpected": (
        "Ha ocurrido un error inesperado.",
        "Vuelve a intentarlo. Si se repite, cierra y abre de nuevo ExitMap.",
    ),
    "offline": (
        "No hay conexión a Internet o el proveedor de correo no responde.",
        "Comprueba tu conexión y vuelve a intentarlo.",
    ),
    "permission_expired": (
        "El permiso de acceso a la cuenta ha caducado o se ha retirado desde Google o Microsoft.",
        "Vuelve a conectar la cuenta. Tus resultados y estados se conservan.",
    ),
    "authorization_denied": (
        "Se ha cancelado o denegado la autorización, así que no se ha añadido la cuenta.",
        "Si quieres conectarla, vuelve a intentarlo y acepta el permiso de solo lectura.",
    ),
    "authorization_timeout": (
        "La autorización no se ha completado a tiempo en el navegador.",
        "Vuelve a pulsar «Conectar cuenta» y termina la autorización en el navegador.",
    ),
    "authorization_invalid": (
        "La respuesta de autorización recibida no corresponde a esta conexión y se ha rechazado.",
        "Vuelve a pulsar «Conectar cuenta» y completa la autorización desde la ventana que se abra.",
    ),
    "invalid_registration": (
        "Los datos de registro de la app no son válidos.",
        "Revisa que los has copiado completos siguiendo la guía de registro.",
    ),
    "registration_missing": (
        "Faltan los datos de registro de la app para este proveedor de correo.",
        "Sigue la guía de registro y copia en ExitMap los datos que obtengas.",
    ),
    "account_already_connected": (
        "Esta cuenta ya estaba conectada.",
        "",
    ),
    "analysis_in_progress": (
        "Ya hay un análisis en curso.",
        "Espera a que termine o cancélalo antes de iniciar otro.",
    ),
    "invalid_date": (
        "La fecha no es válida.",
        "Escríbela con el formato DD/MM/AAAA, por ejemplo 31/01/2025.",
    ),
    "invalid_date_range": (
        "La fecha de inicio es posterior a la fecha de fin.",
        "Corrige las fechas para que el inicio sea anterior o igual al fin.",
    ),
    "unsubscribe_failed": (
        "La baja automática no ha funcionado.",
        "Se abrirá la página web de baja para que la completes allí.",
    ),
    "catalog_invalid": (
        "No se ha podido leer el catálogo de servicios: falta el fichero o está dañado.",
        "Reinstala ExitMap para recuperar el catálogo.",
    ),
    "wrong_password": (
        "La contraseña maestra es incorrecta.",
        "Vuelve a escribirla. Si la has olvidado, puedes restablecerla y reconectar tus cuentas.",
    ),
    "keyring_unavailable": (
        "No se ha podido usar el llavero del sistema para guardar o leer el acceso a tus cuentas.",
        "Desbloquea el llavero del sistema y vuelve a intentarlo, o activa el modo sesión en los ajustes.",
    ),
}

# Page shown in the browser after the authorization comes back to ExitMap (spec F1-6).
AUTH_PAGE_TITLE = "ExitMap"
AUTH_PAGE_DONE = "Ya puedes cerrar esta pestaña y volver a ExitMap."
AUTH_PAGE_FAILED = "No se ha completado la autorización. Vuelve a ExitMap para ver qué ha pasado."

# Analysis options (spec F2-1, F2-3, F8-1, F8-2).
PERIOD_WHOLE_MAILBOX = "Buzón entero"
PERIOD_LAST_YEAR = "Último año"
PERIOD_CUSTOM = "Rango de fechas personalizado"
MODE_ALL = "Todos los correos"
MODE_NEW_ONLY = "Solo los correos nuevos desde el último análisis"
REANALYSIS_NOTICE = (
    "Esta cuenta ya se ha analizado antes. Se mantendrán los estados que hayas asignado "
    "a cada servicio."
)

# Empty results (spec F2-10, F3-5).
NO_SERVICES_FOUND = (
    "El análisis ha terminado sin encontrar ningún servicio. Prueba a ampliar el periodo "
    "o a incluir Spam y Papelera."
)
NO_MATCHES = "Ningún servicio coincide con la búsqueda o los filtros."

# Unsubscribe confirmation (spec F5-1).
UNSUBSCRIBE_CONFIRM = (
    "¿Darse de baja del correo comercial de {service} en la cuenta {account}?\n\n"
    "Método: {method}."
)
UNSUBSCRIBE_METHOD_LABELS = {
    "one_click": "baja automática",
    "web": "se abrirá esta web: {url}",
    "mailto": "se preparará un correo de baja",
}

# Account removal confirmation (spec F9-1).
REMOVE_ACCOUNT_CONFIRM = (
    "¿Quitar la cuenta {account} de ExitMap?\n\n"
    "Se borrarán de este equipo:\n"
    "- las credenciales de acceso a la cuenta,\n"
    "- los resultados del análisis ({count}),\n"
    "- los estados que hayas asignado a sus servicios.\n\n"
    "Esta acción no se puede deshacer."
)
SERVICE_COUNT_ONE = "1 servicio"
SERVICE_COUNT_MANY = "{count} servicios"

# Labels of the domain values (spec F3-4, F4-1, F7).
STATE_LABELS = {
    "pending": "Pendiente",
    "keep": "Conservar",
    "unsubscribed": "Baja realizada",
    "access_revoked": "Acceso revocado",
    "account_deleted": "Cuenta eliminada",
    "dismissed": "Descartado",
}
RELATION_LABELS = {
    "registered": "Cuenta registrada",
    "subscription": "Suscripción comercial",
    "access": "Acceso/permiso concedido",
}
PROVIDER_LABELS = {
    "gmail": "Gmail",
    "outlook": "Outlook",
}

# Main window (spec F3).
APP_TITLE = "ExitMap"
ACCOUNTS_TITLE = "Cuentas conectadas"
NO_ACCOUNTS = "No hay cuentas conectadas."
ACCOUNT_LABEL = "{email} ({provider})"
SEARCH_LABEL = "Buscar:"
ALL_ACCOUNTS = "Todas las cuentas"
ALL_RELATIONS = "Todos los tipos"
ALL_STATES = "Todos los estados"
COLUMN_NAME = "Servicio"
COLUMN_DOMAIN = "Dominio"
COLUMN_ACCOUNT = "Cuenta"
COLUMN_RELATIONS = "Tipo de relación"
COLUMN_STATE = "Estado"
# Mark of a service that sent email again after unsubscribing (spec F8-4).
ALERT_MARK = "⚠ "
ALERT_HINT = "⚠ Ha vuelto a enviarte correo después de darte de baja."

# Common buttons and dialog titles.
OK = "Aceptar"
CANCEL = "Cancelar"
ERROR_TITLE = "ExitMap: error"
INFO_TITLE = "ExitMap"

# Connect account (spec F1-1, F1-2, F1-6, F1-7).
CONNECT_BUTTON = "Conectar cuenta"
CHOOSE_PROVIDER_TITLE = "Conectar cuenta"
CHOOSE_PROVIDER = "¿Qué tipo de cuenta quieres conectar?"
REGISTRATION_TITLE = "Datos de registro de {provider}"
REGISTRATION_INTRO = (
    "Para conectar cuentas de {provider}, ExitMap necesita los datos de tu propio registro "
    "de la app. Sigue la guía de registro y copia aquí los datos que obtengas."
)
CLIENT_ID = "Client ID:"
CLIENT_SECRET = "Client secret:"
GUIDE_LINK = "Abrir la guía de registro"
WAITING_AUTHORIZATION = (
    "Completa la autorización en el navegador que se ha abierto.\n"
    "ExitMap solo pide permiso para leer tu correo."
)
