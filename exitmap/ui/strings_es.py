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
    "account_already_connected": (
        "Esta cuenta ya estaba conectada.",
        "",
    ),
    "analysis_in_progress": (
        "Ya hay un análisis en curso.",
        "Espera a que termine o cancélalo antes de iniciar otro.",
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
