# Spec — ExitMap v1

## 1. Objetivo

Muchas personas no saben en qué servicios están registradas ni de cuáles reciben
correo comercial. ExitMap analiza una o varias cuentas de correo del usuario final y le
muestra:

- en qué servicios tiene una cuenta registrada,
- de qué servicios recibe correo comercial o newsletters porque está suscrito,
- a qué servicios ha concedido accesos o permisos,

y le lleva, desde la app, al punto donde puede darse de baja, eliminar su cuenta o
retirar esos accesos.

**Criterio de éxito:** el usuario final ha podido llegar, desde la app, al punto de baja,
borrado o gestión de permisos de cada servicio que eligió.

## 2. Usuarios

- **Usuario final no técnico:** quiere saber dónde está registrado y reducir el correo
  comercial sin entender cómo funciona por dentro.
- **Usuario final técnico / preocupado por la privacidad:** quiere un inventario completo,
  con evidencias, y control sobre qué se analiza.

Ambos pueden conectar varias cuentas de correo (Gmail y Outlook).

Antes de conectar la primera cuenta de cada proveedor, el usuario final tiene que crear su
propio registro de la app en Google y/o Microsoft siguiendo la guía de registro
(`docs/guia-registro.md`, enlazada desde el README). El usuario final no técnico
necesitará seguir esa guía (o recibir ayuda) la primera vez.

La interfaz de la v1 está en español.

## 3. Glosario

- **Servicio:** empresa o web identificada por el dominio registrable del remitente (p. ej.
  `news.amazon.es` → `amazon.es`). En la v1, cada dominio
  es un servicio distinto y cada par (servicio, cuenta de correo) es una entrada distinta
  de la lista.
- **Tipo de relación:** *cuenta registrada*, *suscripción comercial* o *acceso/permiso
  concedido*. Un servicio puede tener varios.
- **Evidencia:** los correos (asunto y fecha) en los que se basa la detección.
- **Enlace de gestión:** la página donde el usuario final puede darse de baja, eliminar la
  cuenta o revocar accesos.
- **Análisis completo:** análisis que ha terminado sin cancelarse ni interrumpirse.
- **Baja automática:** baja que la app realiza por sí misma, sin que el usuario final tenga
  que salir de ella y sin enviar ningún correo.

## 4. Funcionalidades

### F1. Conectar cuentas de correo

**Historia:** Como usuario final, quiero conectar una o varias cuentas de Gmail u Outlook
para que ExitMap pueda analizarlas.

**Criterios de aceptación:**
1. Dado que no hay cuentas conectadas, cuando el usuario final elige "Conectar cuenta",
   entonces puede elegir entre Gmail y Outlook.
2. Dado que no hay registro configurado para el proveedor elegido, cuando el usuario final
   elige conectar, entonces la app le pide los datos de su registro y le enlaza a la guía;
   si los datos son incorrectos, la app explica qué falla.
3. Dado que el usuario final autoriza el acceso, cuando la conexión termina, entonces la
   cuenta aparece en la lista de cuentas conectadas, con su dirección de correo.
4. Dado que la app pide permisos al proveedor, cuando se muestra la pantalla de
   autorización, entonces solo se pide acceso de lectura al correo.
5. Dado que hay una cuenta conectada, cuando el usuario final conecta otra, entonces
   ambas aparecen en la lista de cuentas conectadas.
6. Dado que el usuario final cancela o deniega la autorización, cuando vuelve a la app,
   entonces no se añade ninguna cuenta y se muestra un mensaje que explica qué ha pasado.
7. Dado que una cuenta ya está conectada, cuando el usuario final vuelve a conectarla,
   entonces no se duplica y se le informa de que ya estaba conectada.

### F2. Analizar el buzón

**Historia:** Como usuario final, quiero analizar mi correo, eligiendo qué periodo y qué
carpetas, para descubrir con qué servicios tengo relación.

**Criterios de aceptación:**
1. Dado que el usuario final va a iniciar un análisis, cuando ve las opciones de periodo,
   entonces puede elegir "Buzón entero" (seleccionado por defecto), "Último año" o
   "Rango de fechas personalizado".
2. Dado que elige "Rango de fechas personalizado", cuando la fecha de inicio es posterior a
   la de fin, entonces no puede iniciar el análisis y se le indica el motivo.
3. Dado que el usuario final va a iniciar un análisis, cuando ve las opciones de carpetas,
   entonces puede incluir Spam y/o Papelera, y ambas están desactivadas por defecto.
4. Dado que hay un análisis en curso, cuando el usuario final mira la pantalla, entonces ve
   el número de correos procesados respecto al total (p. ej. "1.200 de 15.000").
5. Dado que hay un análisis en curso, cuando el usuario final pulsa "Cancelar", entonces el
   análisis se detiene, se descartan sus resultados y se conservan los del último análisis
   completo (si existe).
6. Dado que el análisis se interrumpe (pérdida de conexión o cierre de la app), cuando el
   usuario final vuelve a la app, entonces se descartan los resultados de ese análisis, se
   conservan los del último análisis completo y se le informa de que debe empezar de nuevo.
7. Dado un buzón de prueba con correos conocidos de registro, de suscripción comercial y de
   acceso concedido, cuando termina el análisis, entonces cada servicio del buzón de prueba
   aparece con el tipo o los tipos de relación que le corresponden.
8. Dado que termina un análisis completo, cuando el usuario final cierra y vuelve a abrir la
   app, entonces ve la lista de servicios de ese análisis sin tener que analizar de nuevo.
9. Dado que hay un análisis en curso, cuando el usuario final intenta iniciar otro (en
   cualquier cuenta), entonces no puede hacerlo y se le indica que espere a que termine o
   lo cancele.
10. Dado que termina un análisis completo sin detectar ningún servicio, cuando el usuario
    final ve el resultado, entonces se muestra un mensaje que lo indica y sugiere ampliar
    el periodo o incluir otras carpetas.

### F3. Ver y filtrar la lista de servicios

**Historia:** Como usuario final, quiero ver todos los servicios detectados y encontrar
rápidamente los que me interesan.

**Criterios de aceptación:**
1. Dado que un mismo servicio aparece en dos cuentas, cuando el usuario final ve la lista,
   entonces aparecen dos entradas, una por cuenta.
2. Dado que hay servicios en la lista, cuando el usuario final la abre, entonces aparecen
   primero los que tienen aviso (F8), después los que están en estado *pendiente* y después
   el resto. Dentro de cada grupo se ordenan por nombre.
3. Dado que el usuario final escribe en el buscador, cuando el texto coincide con parte del
   nombre o del dominio de un servicio, entonces la lista muestra solo esos servicios.
4. Dado que el usuario final aplica filtros por cuenta, tipo de relación y/o estado, cuando
   se aplican, entonces la lista muestra solo los servicios que cumplen todos los filtros.
5. Dado que ningún servicio cumple la búsqueda o los filtros, cuando se aplican, entonces
   se muestra un mensaje que lo indica.

### F4. Ver la ficha de un servicio

**Historia:** Como usuario final, quiero ver el detalle de un servicio para entender qué
relación tengo con él y si la detección es fiable.

**Criterios de aceptación:**
1. Dado un servicio de la lista, cuando el usuario final abre su ficha, entonces ve: nombre,
   dominio, cuenta de correo, tipos de relación, fecha del primer y del último correo,
   número de correos, estado y enlace de gestión.
2. Dado un servicio, cuando el usuario final abre su ficha, entonces ve la evidencia: la
   lista de correos (asunto y fecha) en los que se basa la detección.
3. Dado un servicio, cuando la app busca su enlace de gestión, entonces lo obtiene en este
   orden: 1) catálogo de la app, 2) enlace en los correos del servicio, 3) web principal
   del dominio.
4. Dado un servicio con enlace de gestión, cuando el usuario final ve la ficha, entonces se
   indica de dónde viene el enlace ("catálogo", "correo" o "web principal").

### F5. Darse de baja de una suscripción comercial

**Historia:** Como usuario final, quiero darme de baja del correo comercial de un servicio
desde la app.

**Criterios de aceptación:**
1. Dado un servicio con relación *suscripción comercial*, cuando el usuario final pulsa
   "Darse de baja", entonces ve una confirmación con el servicio, la cuenta y el método
   ("baja automática", "se abrirá esta web: <url>" o "se preparará un correo de baja"), y
   no se hace nada hasta que confirme.
2. Dado que el servicio ofrece baja automática, cuando el usuario final confirma y la baja
   tiene éxito, entonces el estado pasa a *baja realizada* y se le informa.
3. Dado que la baja automática falla, cuando ocurre el fallo, entonces la app explica el
   motivo, abre el enlace web de baja como alternativa y el estado no cambia.
4. Dado que el servicio no ofrece baja automática pero sí un enlace web de baja, cuando el
   usuario final confirma, entonces se abre ese enlace en el navegador y el estado no
   cambia (el usuario final lo marca él mismo, F7).
5. Dado que el único método de baja que ofrece el servicio es enviar un correo, cuando el
   usuario final confirma, entonces la app se lo explica y abre su programa de correo con
   el mensaje de baja ya preparado, sin enviarlo; el estado no cambia.
6. Dado que el usuario final cancela la confirmación, cuando la cierra, entonces no se
   realiza ninguna acción.

### F6. Ir a eliminar la cuenta o revocar accesos

**Historia:** Como usuario final, quiero ir directamente a la página donde puedo eliminar mi
cuenta o retirar los accesos que concedí a un servicio.

**Criterios de aceptación:**
1. Dado un servicio con enlace de gestión, cuando el usuario final pulsa "Eliminar cuenta" o
   "Revocar acceso", entonces se abre ese enlace en el navegador del sistema.
2. Dado que se abre el enlace, cuando el usuario final vuelve a la app, entonces el estado
   del servicio no cambia automáticamente.

### F7. Asignar estado a un servicio

**Historia:** Como usuario final, quiero marcar qué he hecho con cada servicio para llevar
el control.

**Estados:**

| Estado | Lo asigna |
|---|---|
| Pendiente | La app, por defecto |
| Conservar | El usuario final |
| Baja realizada | La app (baja automática con éxito) o el usuario final |
| Acceso revocado | El usuario final |
| Cuenta eliminada | El usuario final |
| Descartado (no es un servicio mío o está mal detectado) | El usuario final |

**Criterios de aceptación:**
1. Dado un servicio recién detectado, cuando aparece en la lista, entonces su estado es
   *pendiente*.
2. Dado un servicio, cuando el usuario final elige un estado de la tabla, entonces el
   servicio pasa a ese estado y lo mantiene al cerrar y reabrir la app.

### F8. Re-analizar

**Historia:** Como usuario final, quiero volver a analizar mi correo sin perder lo que ya he
decidido sobre cada servicio.

**Criterios de aceptación:**
1. Dado que existe un análisis anterior, cuando el usuario final inicia uno nuevo, entonces
   puede elegir "Todos los correos" o "Solo los correos nuevos desde el último análisis".
2. Dado que existe un análisis anterior, cuando el usuario final inicia uno nuevo, entonces
   se le informa, antes de empezar, de que se mantendrán los estados asignados.
3. Dado un servicio con estado asignado, cuando termina el re-análisis, entonces conserva
   su estado.
4. Dado un servicio en estado *baja realizada*, cuando el re-análisis encuentra correos
   suyos con fecha posterior al cambio a ese estado, entonces el servicio aparece destacado
   con un aviso en la lista.
5. Dado un servicio con aviso, cuando el usuario final abre su ficha, entonces el aviso
   desaparece.
6. Dado un servicio de un análisis anterior que no aparece en un re-análisis completo,
   cuando termina el re-análisis, entonces el servicio se mantiene con sus datos y su estado.

### F9. Quitar una cuenta y borrar sus datos

**Historia:** Como usuario final, quiero desconectar una cuenta y que no quede ningún dato
suyo en mi equipo ni ningún permiso activo.

**Criterios de aceptación:**
1. Dada una cuenta conectada, cuando el usuario final pulsa "Quitar cuenta", entonces ve una
   confirmación que indica qué se borrará (credenciales, resultados del análisis y estados) y
   no se hace nada hasta que confirme.
2. Dado que el usuario final confirma, cuando termina el proceso, entonces la cuenta y todos
   sus servicios desaparecen de la app, y al reabrirla no reaparecen.
3. Dada una cuenta de Gmail, cuando el usuario final confirma y termina el proceso, entonces
   la app ha retirado su permiso de acceso en Google.
4. Dada una cuenta de Outlook (Microsoft no permite que la app retire su propio permiso), o
   dado que no se puede retirar el permiso en Google (p. ej. sin conexión), cuando termina el
   proceso, entonces los datos locales se borran igualmente y se informa al usuario final de
   que debe retirar el permiso manualmente, indicándole dónde.

### F10. Guardar credenciales

**Historia:** Como usuario final, quiero que el acceso a mis cuentas se guarde de forma
segura, o no se guarde si así lo prefiero.

**Criterios de aceptación:**
1. Dado que el sistema tiene llavero disponible y el modo sesión está desactivado, cuando el
   usuario final conecta una cuenta, entonces las credenciales se guardan en el llavero y,
   al reabrir la app, la cuenta sigue conectada.
2. Dado que el sistema no tiene llavero, cuando el usuario final conecta su primera cuenta,
   entonces debe elegir entre crear una contraseña maestra o usar el modo sesión. Si elige
   el modo sesión, queda activado como ajuste (F10-6) y no se le vuelve a preguntar.
3. Dado que se usa contraseña maestra, cuando el usuario final abre la app, entonces se le
   pide la contraseña antes de acceder a sus cuentas.
4. Dado que se usa contraseña maestra, cuando el usuario final introduce una incorrecta,
   entonces se le indica que es incorrecta y puede volver a intentarlo.
5. Dado que el usuario final ha olvidado la contraseña maestra, cuando elige
   restablecerla, entonces se borran las credenciales cifradas, crea una contraseña nueva y
   debe reconectar sus cuentas; los resultados y los estados se conservan.
6. Dado cualquier sistema, cuando el usuario final activa el modo sesión en los ajustes,
   entonces las credenciales no se guardan en disco y se borran las que ya estuvieran
   guardadas; las cuentas siguen en la lista, pero debe reconectarlas.
7. Dado que el modo sesión está activo, cuando el usuario final cierra y reabre la app,
   entonces debe reconectar sus cuentas, y los resultados y los estados se conservan.

## 5. Casos límite y errores

- **Sin conexión al abrir la app:** se muestra la lista guardada. "Analizar", la baja
  automática y la retirada del permiso al quitar una cuenta indican que hace falta conexión.
  Las acciones que solo abren el navegador o el programa de correo siguen disponibles.
- **Pérdida de conexión durante el análisis:** se aplica F2-6.
- **Permiso caducado o retirado desde Google/Microsoft:** la app indica qué cuenta está
  afectada y ofrece volver a conectarla, sin perder los resultados ni los estados guardados.
- **Análisis sin servicios detectados:** se aplica F2-10.
- **Cuenta ya conectada:** se aplica F1-7.
- **Servicio sin enlace en catálogo ni en correos:** se usa la web principal del dominio
  (F4-3).
- **Llavero no disponible al guardar o leer credenciales** (bloqueado o acceso denegado):
  se indica que no se ha podido usar el llavero y se propone desbloquearlo o activar el modo
  sesión.
- **Fichero de credenciales cifradas dañado:** se trata como contraseña incorrecta; el
  usuario final puede restablecerla (F10-5) sin perder resultados ni estados.
- **Cualquier error:** el mensaje indica qué ha fallado y, si existe, la solución más
  probable, sin mostrar contenido de correos ni credenciales (constitución, 5 y 6).

## 6. Fuera de alcance / futuro

- Solicitar la eliminación de datos (envío y seguimiento), con el estado *solicitud enviada*.
- Baja automática mediante envío de correo desde la app.
- Baja en lote (varios servicios con una confirmación).
- Ordenación configurable de la lista.
- Otros proveedores además de Gmail y Outlook (IMAP genérico, Yahoo…).
- Eliminar cuentas o revocar accesos directamente desde la app (en la v1 solo se abre la web).
- Agrupar en un servicio los dominios de una misma empresa.
- Varios análisis simultáneos.
- Exportar los resultados (CSV o PDF).
- Interfaz en inglés.
