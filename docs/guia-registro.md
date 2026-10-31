# Guía de registro de ExitMap en Google y Microsoft

ExitMap no tiene servidores propios: cada persona usa **su propio registro** de la app en
Google (para Gmail) y en Microsoft (para Outlook/Hotmail). Así, el acceso a tu correo solo
pasa entre tu equipo y tu proveedor de correo.

Solo tienes que hacer el registro **una vez por proveedor**. Después, todas las cuentas de
ese proveedor que conectes usan el mismo registro. Si solo vas a conectar cuentas de Gmail,
basta con la parte de Google; si solo vas a conectar cuentas de Outlook, basta con la de
Microsoft.

Los nombres de los menús pueden cambiar un poco con el tiempo; si no encuentras uno,
busca en la consola el nombre que aparece en esta guía.

---

## 1. Google (cuentas de Gmail)

Necesitas una cuenta de Google. Puede ser la misma que vas a analizar.

### 1.1. Crear un proyecto

1. Entra en la consola de Google Cloud: <https://console.cloud.google.com/>.
2. Acepta las condiciones si es la primera vez. No hace falta activar la facturación ni
   introducir una tarjeta.
3. En el selector de proyectos (arriba, junto al logotipo), pulsa **Nuevo proyecto**.
4. Ponle un nombre, por ejemplo `ExitMap`, y pulsa **Crear**. Comprueba que el proyecto
   nuevo queda seleccionado en el selector.

### 1.2. Activar la API de Gmail

1. Abre **APIs y servicios → Biblioteca**
   (<https://console.cloud.google.com/apis/library>).
2. Busca **Gmail API**, ábrela y pulsa **Habilitar**.

### 1.3. Configurar la pantalla de consentimiento

Es la pantalla que Google mostrará cuando conectes tu cuenta desde ExitMap.

1. Abre **Google Auth Platform** (<https://console.cloud.google.com/auth/overview>) y pulsa
   **Comenzar** (o **Empezar**).
2. **Información de la aplicación:** nombre de la app (por ejemplo `ExitMap`) y tu correo
   como correo de asistencia.
3. **Público:** elige **Externo**.
4. **Información de contacto:** tu correo.
5. Acepta la política de datos de usuario de los servicios de API de Google y pulsa
   **Crear**.

### 1.4. Añadir el permiso de solo lectura

1. En Google Auth Platform, abre **Acceso a datos** y pulsa **Añadir o quitar permisos**.
2. Busca y marca este permiso (aparece como "Ver tus mensajes de correo electrónico y tu
   configuración"):

   ```
   https://www.googleapis.com/auth/gmail.readonly
   ```

   Si no aparece en la lista, pégalo en el cuadro de añadir permisos manualmente.
3. Pulsa **Actualizar** y después **Guardar**.

ExitMap solo pide este permiso: puede leer tu correo, pero no enviar, borrar ni modificar
nada. Lo necesita para leer los enlaces de gestión que vienen dentro de algunos correos.

### 1.5. Publicar la app (en producción, sin verificar)

1. En Google Auth Platform, abre **Público**.
2. En **Estado de publicación**, pulsa **Publicar aplicación** y confirma. El estado pasa a
   **En producción**.

No envíes la app a verificación: no hace falta para uso propio. Se publica porque, en el
estado **Prueba**, Google retira el acceso cada 7 días y tendrías que volver a conectar la
cuenta cada semana.

### 1.6. Crear el cliente de escritorio

1. En Google Auth Platform, abre **Clientes** y pulsa **Crear cliente**.
2. **Tipo de aplicación:** elige **Aplicación de escritorio**.
3. Ponle un nombre, por ejemplo `ExitMap escritorio`, y pulsa **Crear**.
4. Se muestran el **ID de cliente** (Client ID) y el **Secreto del cliente** (Client
   secret). **Cópialos ahora** o pulsa **Descargar JSON** y guarda el fichero en un lugar
   seguro de tu equipo: Google puede no volver a mostrar el secreto completo. Si lo
   pierdes, puedes añadir un secreto nuevo desde la ficha del cliente.

El secreto de un cliente de escritorio no se considera confidencial (Google lo trata así
porque va dentro de la app), pero no hace falta compartirlo con nadie.

### 1.7. Datos que pegar en ExitMap

Cuando conectes tu primera cuenta de Gmail, ExitMap te pedirá:

| Campo de ExitMap | Dónde está en Google |
|---|---|
| **Client ID** | ID de cliente (termina en `.apps.googleusercontent.com`) |
| **Client secret** | Secreto del cliente (empieza normalmente por `GOCSPX-`) |

### 1.8. Aviso de "app no verificada"

Al autorizar, Google mostrará **"Google no ha verificado esta aplicación"**. Es normal:
la app es tuya y no la has enviado a verificación. Para continuar:

1. Comprueba que el nombre de la app y el correo de asistencia son los que pusiste en el
   paso 1.3.
2. Pulsa **Configuración avanzada** (o **Avanzado**).
3. Pulsa **Ir a ExitMap (no seguro)**.
4. Revisa que solo se pide ver tu correo y pulsa **Continuar**.

Puedes retirar este permiso cuando quieras en
<https://myaccount.google.com/permissions>. ExitMap también lo retira al quitar la cuenta.

---

## 2. Microsoft (cuentas de Outlook y Hotmail)

### 2.1. Registrar la app

1. Entra en el centro de administración de Microsoft Entra: <https://entra.microsoft.com/>
   (o en el portal de Azure, <https://portal.azure.com/>, servicio **Microsoft Entra ID**).
2. Abre **Identidad → Aplicaciones → Registros de aplicaciones** y pulsa **Nuevo
   registro**.
   - Si el portal te indica que no tienes acceso a los registros de aplicaciones, tu
     cuenta necesita un directorio (inquilino) de Microsoft Entra. Se obtiene gratis al
     crear una cuenta de Azure.
3. Rellena el formulario:
   - **Nombre:** por ejemplo `ExitMap`.
   - **Tipos de cuenta admitidos:** **Cuentas en cualquier directorio organizativo y
     cuentas de Microsoft personales (como Skype o Xbox)**. Es imprescindible para poder
     conectar cuentas de Outlook.com y Hotmail.
   - **URI de redirección:** elige la plataforma **Cliente público/nativo (móvil y
     escritorio)** y escribe:

     ```
     http://localhost
     ```

     Sin puerto ni nada más: ExitMap usa un puerto distinto cada vez y Microsoft no tiene
     en cuenta el puerto en `localhost`.
4. Pulsa **Registrar**.

No crees ningún secreto de cliente ni certificado: ExitMap es un cliente público y no lo
usa.

### 2.2. Comprobar la plataforma (si no la elegiste al registrar)

1. En la app registrada, abre **Autenticación**.
2. Si no aparece **Aplicaciones móviles y de escritorio**, pulsa **Agregar una plataforma →
   Aplicaciones móviles y de escritorio**, escribe `http://localhost` en **URI de
   redireccionamiento personalizados** y pulsa **Configurar**.

No hace falta añadir permisos en **Permisos de API**: ExitMap pide al conectar solo los que
necesita (`Mail.Read`, de solo lectura, y los básicos para identificar la cuenta y mantener
el acceso: `offline_access`, `openid` y `email`), y tú los aceptas en la pantalla de
Microsoft.

### 2.3. Datos que pegar en ExitMap

En la página **Información general** de la app registrada:

| Campo de ExitMap | Dónde está en Microsoft |
|---|---|
| **Client ID** | **Id. de aplicación (cliente)** (formato `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) |

Para Outlook ExitMap no pide secreto.

### 2.4. Retirar el permiso

Microsoft no permite que una app retire su propio permiso en las cuentas personales. Al
quitar una cuenta de Outlook en ExitMap, retíralo tú en
<https://account.live.com/consent/Manage>.

---

## 3. Conectar la cuenta en ExitMap

1. Abre ExitMap y pulsa **Conectar cuenta**.
2. Elige **Gmail** u **Outlook**.
3. La primera vez, pega los datos del apartado 1.7 (Google) o 2.3 (Microsoft) y pulsa
   **Aceptar**.
4. Se abrirá el navegador: inicia sesión con la cuenta que quieres analizar y acepta el
   permiso de solo lectura. Tienes 5 minutos para completarlo.
5. Vuelve a ExitMap: la cuenta aparecerá en la lista de cuentas conectadas.

## 4. Problemas frecuentes

| Problema | Causa probable y solución |
|---|---|
| ExitMap dice que los datos de registro no son válidos | Falta algún dato o no está completo. Vuelve a copiarlos (apartado 1.7 o 2.3). |
| Google muestra `invalid_client` | El Client ID o el Client secret no son correctos, o el cliente se ha borrado. Cópialos de nuevo o crea otro cliente (apartado 1.6). |
| Google muestra "Acceso bloqueado" o `access_denied` | La app sigue en estado **Prueba** y tu cuenta no está como usuario de prueba. Publícala (apartado 1.5). |
| Google muestra que la API de Gmail no está habilitada | Activa la API (apartado 1.2) en el mismo proyecto del cliente. |
| Microsoft muestra `unauthorized_client` o que la app no admite cuentas personales | Revisa los **tipos de cuenta admitidos** (apartado 2.1). Si es necesario, crea un registro nuevo con el tipo correcto. |
| Microsoft muestra `redirect_uri` no válida | Revisa que la plataforma es **Aplicaciones móviles y de escritorio** y la URI es exactamente `http://localhost` (apartado 2.2). |
| El navegador no vuelve a ExitMap | Han pasado más de 5 minutos o se cerró la ventana. Vuelve a pulsar **Conectar cuenta**. |
| Tras unos días hay que volver a conectar la cuenta de Gmail | La app de Google sigue en estado **Prueba**. Publícala (apartado 1.5) y vuelve a conectar la cuenta. |
