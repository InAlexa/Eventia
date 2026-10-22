@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto usepy
python manage.py seed
if errorlevel 1 goto failed
start "" "http://127.0.0.1:8000"
python manage.py run
goto end
:usepy
py manage.py seed
if errorlevel 1 goto failed
start "" "http://127.0.0.1:8000"
py manage.py run
goto end
:failed
echo No se pudo iniciar Eventia. Instala Python 3.11 o posterior y revisa el README.
:end
pause
