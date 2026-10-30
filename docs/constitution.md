# Constitución de ExitMap

Principios no negociables del proyecto. Toda spec, plan e implementación debe cumplirlos.

En este documento, **desarrollador** es quien construye ExitMap y **usuario final** es quien usa la aplicación.

## Calidad y tests

1. **Compatibilidad con varios proveedores de correo.** El código no se acopla a un proveedor concreto. La lógica de cada proveedor queda aislada y se prueba por separado.
2. **Cobertura mínima del 75 %.** Toda funcionalidad tiene al menos un test unitario y uno de integración, y la cobertura total es ≥ 75 %.

## Dependencias y simplicidad

3. **Dependencias fiables y validadas.** Solo se usan la librería estándar o dependencias que cumplan todos estos criterios: mantenimiento activo, licencia compatible con el proyecto, sin vulnerabilidades conocidas y uso extendido. Antes de añadir una dependencia nueva, se comprueban estos criterios y se comunica al desarrollador.
4. **Simplicidad proporcional.** Se usan soluciones simples para los aspectos comunes y generales. Solo se recurre a soluciones más complejas cuando son necesarias, y se justifica por escrito en el plan.

## Errores y seguridad

5. **Errores comprensibles.** Ante un error, la aplicación muestra al usuario final un mensaje personalizado que indica qué está fallando o qué ha fallado y, si existe, la solución más probable.
6. **Privacidad y datos en local.** Las credenciales, los correos y los resultados del análisis se procesan y almacenan solo en el equipo del usuario final, y nadie ajeno a él puede acceder a ellos. En concreto:
   - Las únicas conexiones externas son las imprescindibles: el proveedor de correo y los destinatarios de las solicitudes que el usuario final haya aprobado.
   - Sin telemetría ni servidores propios.
   - Las credenciales se guardan en el llavero del sistema o, si no está disponible, cifradas.
   - Los logs y los mensajes de error no incluyen contenido de correos ni credenciales.
7. **Mínimos privilegios.** Se piden los permisos mínimos necesarios (por ejemplo, OAuth de solo lectura) y solo se amplían cuando una funcionalidad lo requiere, con confirmación del usuario final.
8. **Confirmación informada antes de acciones irreversibles.** Eliminar, revocar, solicitar el borrado de datos o enviar cualquier correo en nombre del usuario final siempre requiere su confirmación explícita.

## Proceso

- Si un test falla, se comunica al desarrollador, se explica la causa y se propone una solución.
- Si la spec y la implementación no coinciden, o surge una decisión no prevista, se comunica al desarrollador y se propone dónde aplicar el cambio: en la spec o en el código.
