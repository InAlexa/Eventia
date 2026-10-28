@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto usepy
python manage.py seed
if errorlevel 1 goto failed
python start_eventia.py
if errorlevel 1 goto failed
goto end
:usepy
py manage.py seed
if errorlevel 1 goto failed
py start_eventia.py
if errorlevel 1 goto failed
goto end
:failed
echo Eventia could not start. Check Python errors and whether port 8000 is available.
pause
:end
endlocal
