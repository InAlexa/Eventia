# Corrección: organizar con una cuenta existente

El registro público crea asistentes, como exige el modelo de permisos. El botón Quiero organizar mostraba un texto de registro cuando no existía sesión activa; además, el flujo no retomaba la intención de organizar después de iniciar sesión.

Cambios:

- Comprobar sesión actual antes de decidir el acceso.
- Si no hay sesión, abrir Iniciar sesión; conservar Crear cuenta como alternativa secundaria.
- Retomar la acción de organizar después del acceso, incluyendo el cambio entre registro e inicio de sesión.
- Para asistentes autenticados, indicar que su cuenta ya existe y que falta permiso de organizador, sin pedir duplicar la cuenta.
- Agregar `manage.py set-role --correo CORREO --rol organizador` para administrar cuentas existentes desde la instalación local. Conserva ID, contraseña y relaciones, y revoca sus sesiones anteriores. No se agregó un endpoint público para autoasignarse roles.

Verificación: `node --check public/app.js`, cinco pruebas de decisiones de interfaz en `tests/test_organize.cjs` y dos pruebas de cuenta existente en `tests/test_roles.py`, todas correctas. Las pruebas de interfaz usan un DOM simulado; no se afirma una revisión visual en navegador. La ejecución anterior de las 28 pruebas HTTP/negocio sigue documentada en `pruebas.txt`; no se volvió a ejecutar esa batería para este cambio sin modificaciones del backend HTTP.

Al actualizar otra copia, reemplazar los archivos del proyecto y conservar su carpeta `data/`. Para habilitar la cuenta, el administrador debe usar Usuarios o el comando local; después el titular inicia sesión de nuevo. El ZIP excluye bases de datos y secretos.
