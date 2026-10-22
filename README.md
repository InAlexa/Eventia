# Eventia

Plataforma de eventos gratuitos construida a partir de los cuatro PDF proporcionados. Incluye interfaz adaptable a móvil, API real, base de datos persistente, autenticación y controles de seguridad.

## Iniciar en Windows

Requisito: Python 3.11 o posterior. Abre una terminal en esta carpeta:

```powershell
python manage.py seed
python manage.py run
```

Abre http://127.0.0.1:8000. Si Windows usa el lanzador `py`, reemplaza `python` por `py`. También puedes ejecutar `Iniciar Eventia.cmd`. Los datos locales se guardan en `data/eventia.db` y permanecen después de cerrar el servidor. Para detenerlo: Ctrl+C.

El catálogo inicial tiene seis eventos ficticios. Sus fechas se calculan al ejecutar `seed` por primera vez. No existen contraseñas públicas ni accesos privilegiados automáticos. Regístrate desde la interfaz para probar el flujo de asistente. Todos los eventos son gratuitos, como define el MVP; no hay cobros.

## Organizador y administrador

Crea cuentas desde la terminal; la contraseña se pide de forma oculta:

```powershell
python manage.py create-user --correo organizador@example.com --nombre "Organizador" --rol organizador
python manage.py create-user --correo admin@example.com --nombre "Administrador" --rol administrador
```

Inicia sesión con esas cuentas para ver **Organizar** o **Usuarios**. Los organizadores crean y editan sus propios eventos y consultan sus asistentes. El administrador puede asignar roles a otras cuentas desde Usuarios. El registro público siempre crea asistentes y rechaza propiedades como `rol`. El administrador tiene facultad de editar eventos ajenos mediante la API; su vista Mis eventos muestra únicamente los propios.

### Ya tengo cuenta, pero no puedo crear eventos

No necesitas crear otra cuenta. Registro e inicio de sesión no conceden automáticamente el permiso de organizador. Si administras esta instalación local, habilita tu cuenta existente desde una terminal en esta carpeta:

```powershell
python manage.py set-role --correo "TU_CORREO_REGISTRADO" --rol organizador
```

Reemplaza TU_CORREO_REGISTRADO por el correo con el que ya te registraste. Se conserva la cuenta, contraseña e inscripciones; se cierran sus sesiones. Inicia sesión de nuevo y entra en **Organizar → Crear evento**. En Docker usa `docker compose exec web python manage.py set-role --correo "TU_CORREO_REGISTRADO" --rol organizador`. La alternativa desde la interfaz es que un administrador cambie tu rol en **Usuarios**.

El botón **Quiero organizar** comprueba la sesión actual, permite iniciar sesión con una cuenta existente y retoma la acción al terminar. Si la cuenta es asistente, explica el permiso faltante sin pedir un nuevo registro.

## Qué incluye

- Catálogo con búsqueda por título/descripción, filtro por categoría y orden por fecha, nombre o disponibilidad.
- Registro y acceso por correo y contraseña. Sesiones persistidas en servidor, cookies HttpOnly y SameSite, expiración de ocho horas, cierre e invalidación.
- Creación y edición de eventos con validación de título, fecha, cupo, ubicación y precio gratuito.
- Una inscripción por persona y evento, cupos transaccionales, historial personal y lista restringida de asistentes.
- Prevención de asignación masiva, control de propiedad y rol, DTO de perfil sin datos de contraseña, consultas parametrizadas, escape HTML y CSP.
- Limitación de intentos de acceso por cuenta e IP, de registros por IP y de inscripciones por usuario.
- Outbox transaccional para confirmaciones por correo, worker SMTP con reintentos.
- Auditoría, rediseño de las siete operaciones, matriz de permisos, respuestas de la actividad, OpenAPI y pruebas reproducibles.

## Documentación y pruebas

```powershell
python -m unittest discover -s tests -v
```

Para las regresiones de la interfaz (sin dependencias, con Node.js instalado):

```powershell
node --test tests/test_organize.cjs
```

Corrección del flujo de organización: se verificaron cinco casos de sesión/rol usando el código real de la interfaz con un DOM simulado y dos pruebas de la CLI para habilitar cuentas existentes. Las siete pruebas pasaron. Estas pruebas no sustituyen la revisión visual pendiente en navegador.

- `docs/ACTIVIDAD-23.md`: auditoría, rediseño, permisos, evidencia y respuestas.
- `docs/ARQUITECTURA.md`: módulos, persistencia, límites y evolución.
- `docs/openapi.json`: contrato OpenAPI 3.1 de las siete operaciones auditadas y de la consulta de sesión. Se puede importar en Postman o un editor OpenAPI. También disponible en `/openapi.json` con el servidor abierto.
- `docs/pruebas.txt`: salida real de la ejecución de pruebas en SQLite.
- `tests/test_security.py`: pruebas HTTP, negocio, concurrencia y seguridad. Usan una base temporal aislada y no modifican los datos reales.

Verificación adicional: sintaxis JavaScript correcta y respuestas HTTP 200 de inicio, CSS, JavaScript, catálogo y OpenAPI. La revisión visual automatizada de escritorio/móvil quedó pendiente: el navegador no pudo iniciarse en el entorno. El diseño incluye reglas adaptables y controles accesibles, pero no se afirma haber inspeccionado capturas ni completado una prueba de interfaz en navegador.

## PostgreSQL

Para probar localmente no hacen falta paquetes adicionales. Para la arquitectura PostgreSQL propuesta en los documentos:

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL = 'postgresql://eventia:TU_PASSWORD@127.0.0.1:5432/eventia'
python manage.py seed
python manage.py run
```

La base y el usuario PostgreSQL deben existir. El esquema se crea automáticamente. PostgreSQL usa `SELECT ... FOR UPDATE`; SQLite usa `BEGIN IMMEDIATE`. No se migran automáticamente los datos entre motores. La configuración PostgreSQL está implementada pero no fue ejecutada en este entorno. Las pruebas pueden dirigirse a una **base PostgreSQL vacía de pruebas** mediante `TEST_DATABASE_URL`; cada ejecución necesita una base vacía porque los usuarios de prueba usan correos fijos.

Con Docker instalado, define `POSTGRES_PASSWORD` (usa caracteres alfanuméricos para evitar problemas de URL) y ejecuta:

```powershell
$env:POSTGRES_PASSWORD = 'REEMPLAZA_POR_UN_SECRETO_LARGO'
docker compose up --build -d
docker compose exec web python manage.py seed
docker compose exec web python manage.py create-user --correo admin@example.com --nombre Admin --rol administrador
```

Docker Compose incluye web, PostgreSQL y worker. Esta opción no fue ejecutada en este entorno.

## Correos

Sin SMTP las confirmaciones quedan **pendientes**, no se simula un envío exitoso. Para enviarlas, exporta `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER` y `SMTP_PASSWORD`; inicia `python manage.py worker` en otra terminal con el mismo entorno y la misma base. El worker exige STARTTLS, intenta hasta cinco veces con intervalos de 30 segundos y usa un Message-ID estable. Ejecuta solo un worker: la implementación actual no incluye coordinación entre consumidores. La entrega SMTP es al menos una vez; un fallo entre envío y confirmación puede repetir un mensaje. Tras cinco fallos se requiere revisión manual. En Docker, agrega las variables SMTP a `appenv` en compose.yaml. El envío externo no fue probado, al no contar con credenciales.

## Publicación y alcance

Esta entrega es una aplicación local ejecutable. No se publicó ni se creó un repositorio remoto: no se proporcionó un destino ni una cuenta de despliegue. Sites ejecuta Workers y no hospeda directamente este backend Python con PostgreSQL por TCP. El código se conserva en una carpeta portable y en el ZIP entregado.

Antes de exponerla a Internet, usar un servidor HTTP de producción detrás de un proxy HTTPS; el servidor estándar incluido sirve para desarrollo. Configurar `COOKIE_SECURE=1` y `EVENTIA_ORIGIN=https://tu-dominio`. El valor de Origin debe coincidir exactamente. El proxy debe conservar el encabezado Origin, limitar cuerpos, conexiones y tiempos; debe configurarse de forma que la limitación por IP use una IP verificada. La implementación ignora X-Forwarded-For; detrás de un proxy, las cuentas comparten su cuota de IP. Añadir backups, observabilidad, paginación de listas administrativas y revisión de seguridad antes de un lanzamiento real.

No se implementan pagos, SMS, reseñas, mapas, microservicios, Redis ni analítica avanzada: los documentos los difieren. La confirmación disponible dentro de Mis inscripciones sí funciona sin servicios externos. No se inventó un enlace al repositorio solicitado por la actividad; ese entregable requiere seleccionar un repositorio de destino.
