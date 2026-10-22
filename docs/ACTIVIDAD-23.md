# Eventia: de una API insegura a un diseño seguro

## Auditoría de las siete operaciones

| API | Problema del caso original | Consecuencia | OWASP API Security 2023 | Corrección implementada |
| --- | --- | --- | --- | --- |
| 1. Consulta de inscripción | Solo verifica existencia | Lectura de inscripciones ajenas | API1: Broken Object Level Authorization | Verificar propietario, organizador del evento o administrador |
| 2. Registro | Guarda `rol` recibido | Escalada a administrador | API3: Broken Object Property Level Authorization | Lista de propiedades permitidas, rechazo de rol y asignación en servidor |
| 3. Crear evento | No valida cupo/precio ni rol | Datos imposibles y publicación no autorizada | API5: Broken Function Level Authorization; validación insuficiente como problema adicional | Solo organizador/administrador; cupo entero positivo; MVP precio cero; fecha futura |
| 4. Editar evento | Rol sin propiedad | Sabotaje entre organizadores | API1: Broken Object Level Authorization | Propiedad contextual, excepción administrativa explícita |
| 5. Inscripciones | Cantidad sin límite y reserva sin atomicidad | Acaparamiento y sobrecupo | API6: Unrestricted Access to Sensitive Business Flows; API4 por consumo sin límites | Una plaza y una inscripción por usuario/evento; rate limit; transacción y bloqueo |
| 6. Consulta de usuario | Devuelve campos privados completos | Filtración de hashes y datos innecesarios | API3: Broken Object Property Level Authorization | DTO id/nombre/correo y acceso propio/administrador |
| 7. Inicio de sesión | Intentos ilimitados y errores distintos | Fuerza bruta y enumeración | API2: Broken Authentication; API4 como riesgo adicional | Cuotas por IP/cuenta, error genérico y cálculo de hash para cuentas inexistentes |

La condición de carrera es un fallo de consistencia/diseño; no se fuerza una correspondencia exclusiva con una categoría del Top 10. La asignación anterior utiliza el riesgo API más próximo a cada flujo. El documento previo usa categorías OWASP Web 2021, mientras esta actividad solicita **OWASP API Security 2023**, que es una lista diferente.

Referencia oficial consultada: [OWASP API Security Top 10, edición 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/). Los nombres de categorías se usan como taxonomía; el diagnóstico y las soluciones corresponden a esta implementación.

## Rediseño de operaciones

Todas las respuestas son JSON. Los errores usan `{ "error": "mensaje" }`. Los ID de ruta son enteros positivos. Cuerpos JSON de hasta 16384 bytes; tipos de contenido ajenos reciben 415 y cuerpos vacíos/excesivos 413. Mutaciones autenticadas requieren cookie de sesión y X-CSRF-Token. Se rechazan orígenes ajenos con 403. Las rutas desconocidas reciben 404.

### 1. GET /api/inscripciones/{id}

Función: consultar el comprobante de una inscripción. Sin cuerpo; recibe ID por ruta. Acceso: usuario dueño, organizador dueño del evento o administrador. Validar sesión activa, existencia y relación de propiedad en servidor. Respuesta 200: id, evento_id, usuario_id, fecha. Errores 401 sin sesión, 403 por recurso ajeno, 404 inexistente. No incluye nombres/correos de otros asistentes.

### 2. POST /api/usuarios

Función: crear asistente. Acceso público. Recibe únicamente nombre (2-80 caracteres), correo válido (máximo 254) y password (12-128). Se rechazan campos extra, incluido rol. Normaliza correo, genera hash y fija rol usuario. Cuota de 20 registros por IP/hora. Respuesta 201: id, nombre, correo. Errores 400 validación, 409 conflicto de cuenta, 429 cuota. Si ya existe una sesión, la mutación exige su token CSRF.

### 3. POST /api/eventos

Función: publicar evento. Acceso: organizador o administrador autenticado. Recibe titulo, descripcion, fecha, ubicacion, categoria, cupo y precio. Textos no vacíos: máximo 160 excepto descripción 3000; fecha ISO futura con zona horaria; cupo entero 1-100000; precio entero exactamente 0 en MVP. Rechaza propiedades adicionales como organizador_id y disponibles. El servidor fija propietario y disponibilidad. Respuesta 201: evento creado. Errores 400, 401, 403. El precio cero implementa el requisito más estricto del MVP y también rechaza el precio negativo del caso inseguro.

### 4. PUT /api/eventos/{id}

Función: reemplazar campos editables de un evento. Recibe el cuerpo completo de creación. Acceso: organizador propietario o administrador. Además de las validaciones anteriores, verifica existencia/propiedad y bloquea fila durante la edición. El cupo no puede bajar del número de inscripciones; recalcula disponibles sin modificar organizador_id. Respuesta 200: evento actualizado. Errores 400, 401, 403, 404, 409. La excepción administrativa está definida en la matriz; ser organizador por sí solo no basta.

### 5. POST /api/eventos/{id}/inscripciones

Función: reservar un lugar. Acceso: cualquier usuario autenticado. Recibe exclusivamente `{ "cantidad": 1 }`. La identidad viene de la sesión, no del cuerpo. Valida evento activo/futuro, una plaza por cuenta/evento, ausencia de inscripción previa y disponibilidad bajo bloqueo transaccional. Cuota 20 solicitudes/usuario/minuto. Crea outbox en la misma transacción. Respuesta 201: id, evento_id, usuario_id, fecha, disponibles, notificacion=pendiente. Errores 400, 401, 403 CSRF/origen, 404, 409 duplicado/sin cupo/evento no disponible, 429. La confirmación no implica cobro ni que ya se entregó un correo.

### 6. GET /api/usuarios/{id}

Función: consultar perfil mínimo. Acceso: usuario del perfil o administrador. Sin cuerpo; ID en ruta. Respuesta 200: exclusivamente id, nombre y correo; nunca hash, teléfono ni rol. La sesión propia (`/api/auth/me`) retorna rol para construir navegación y token CSRF; la ruta administrativa de usuarios retorna roles con permiso explícito. Errores 401, 403, 404.

### 7. POST /api/auth/login

Función: autenticar. Público, recibe exclusivamente correo y password. Valida tipos y longitudes, normaliza correo; límite 8 intentos/cuenta y 30/IP por 15 minutos. Calcula PBKDF2 incluso si no existe el correo. Devuelve 200 con usuario mínimo/rol y csrf; Set-Cookie contiene sesión HttpOnly y SameSite=Strict, con Secure en HTTPS. Errores 400 datos inválidos, 401 siempre “Correo o contraseña incorrectos.”, 429 con Retry-After=900. Rechaza origen ajeno 403. Si se llama teniendo sesión válida, exige CSRF y rota/elimina la sesión anterior al completar login.

## Matriz de autorización

| Operación | Visitante | Usuario | Organizador | Administrador |
| --- | --- | --- | --- | --- |
| Consultar eventos públicos | Sí | Sí | Sí | Sí |
| Crear eventos | No | No | Sí | Sí |
| Modificar eventos propios | No | No | Sí, propietario | Sí |
| Modificar eventos ajenos | No | No | No | Sí, excepción administrativa |
| Inscribirse | No | Sí | Sí | Sí |
| Consultar inscripciones propias | No | Sí | Sí | Sí |
| Consultar inscritos de un evento | No | No | Sí, propietario del evento | Sí |
| Administrar usuarios/roles | No | No | No | Sí; no cambiar rol propio |

La propiedad se valida sobre los datos del servidor en cada operación. Ocultar un botón sirve para orientar la interfaz; no reemplaza la autorización. El límite de un cupo también aplica a administradores y organizadores. Ningún rol puede crear eventos con cupo negativo o inscribirse en un evento agotado.

## Evidencia de controles implementados

No se recibió un repositorio anterior; el comportamiento “anterior” se refiere al caso descrito en el PDF, no a una ejecución de código vulnerable. `docs/pruebas.txt` registra la ejecución real del sistema corregido. Las pruebas crean datos temporales e incluyen llamadas HTTP y concurrencia real con dos hilos.

| Control | Antes según caso | Cambio | Prueba válida | Prueba inválida/no autorizada | Resultado observado |
| --- | --- | --- | --- | --- | --- |
| Evitar escalada en registro | Guardaba rol arbitrario | Lista permitida y rol fijo | Registro normal devuelve 201, almacena usuario y hash | Enviar rol administrador devuelve 400 | Tests 02-04 OK |
| Validación y rol de creación | Aceptaba cupo -50/precio -100 y cualquier cuenta | Validación estricta en servicio y control de rol | Organizador crea y obtiene propietario correcto | Cupos -50/0/1.5/bool/texto, precios negativos/pagados/bool devuelven 400; usuario devuelve 403 | Tests 08-12 OK |
| Propiedad de eventos | Un organizador editaba eventos ajenos | Verificación de organizador_id | Dueño puede editar | Otro organizador obtiene 403 y el título se conserva | Tests 13-14 OK |
| Inscripción atómica | Lectura/escritura separadas, cantidades masivas | Transacción, bloqueo, cantidad 1 y unicidad | Inscripción devuelve cupos 10→9 y outbox pendiente | Duplicado 409, cantidad 500→400; último cupo concurrente genera 201 y 409 | Tests 15-17 y 22-23 OK |
| Propiedad de inscripciones | Solo verificaba ID existente | Dueño u organizador contextual/admin | Dueño y organizador del evento pueden consultar | Otro usuario y otro organizador obtienen 403 | Tests 18-19 OK |
| Minimizar perfil | Exponía passwordHash | DTO explícito | Perfil propio 200 con tres campos | Perfil ajeno 403; hash ausente | Test 20 OK |
| Autenticación y CSRF | Errores distintos/intentos ilimitados | Mensaje genérico, cuota, cookie y CSRF | Login 200, cookie HttpOnly; mutación con CSRF 201 | Login ausente/incorrecto responde lo mismo; noveno intento 429; sin CSRF/origen ajeno 403 | Tests 05-07, 21 y 28 OK |

Resultado: **28 pruebas aprobadas con SQLite**. El test de Secure/HSTS verifica los encabezados habilitando COOKIE_SECURE; no certifica que exista infraestructura TLS desplegada. PostgreSQL, Docker y envío SMTP requieren verificarse en el entorno de destino.

## Preguntas finales

**1. ¿Cuál API representa mayor riesgo?** El registro que permite fijar `rol=administrador` es el mayor riesgo en este caso: una persona sin cuenta puede escalar privilegios y obtener acceso a funciones administrativas. La exposición de hashes y el acceso a inscripciones también son graves. La priorización combina alcance y facilidad de explotación; depende de las facultades administrativas reales.

**2. ¿Por qué JWT no garantiza seguridad?** Un token correctamente firmado puede acreditar identidad sin demostrar permiso sobre un evento o inscripción. Se deben verificar firma, algoritmo permitido, emisor, audiencia y expiración, además de autorización por recurso, validación, límites y revocación. Esta implementación elige sesiones en servidor para facilitar la invalidación; tener una sesión tampoco reemplaza los controles de propiedad.

**3. ¿Validar y autorizar?** Validar decide si los datos cumplen las reglas, por ejemplo cupo entero positivo. Autorizar decide si esa persona puede ejecutar la acción sobre ese recurso. Un organizador puede enviar un cuerpo válido y carecer de permiso sobre el evento de otro.

**4. ¿Por qué OpenAPI no implementa seguridad?** OpenAPI describe el contrato esperado. El servidor debe comprobar la cookie, el token CSRF, el rol y la propiedad realmente. Declarar un securityScheme no ejecuta middleware ni impide una llamada no autorizada. Las pruebas contrastan descripción y comportamiento.

**5. ¿Qué conservar al extraer servicios?** Denegación por defecto, identidad verificable entre servicios, autorización contextual en cada límite, validación por listas permitidas, minimización de respuestas, cuotas compartidas, TLS, hashes seguros, auditoría sin secretos y consistencia de cupos. Añadir idempotencia, outbox, deduplicación, reintentos acotados y trazabilidad. Las colas no vuelven automáticamente atómicas las escrituras en servicios distintos.

## Entregables y estado

Código completo, documentación, OpenAPI y evidencia se encuentran en esta carpeta. La publicación en un repositorio remoto queda pendiente de elegir un destino; no hay enlace inventado ni se subieron los PDF a un servicio externo. La aplicación es funcional localmente; no se atribuye preparación para cargas de producción sin las verificaciones descritas en README.
