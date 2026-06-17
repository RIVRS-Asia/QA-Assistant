@echo off
REM Undo setup.bat. Double-click to remove the venv, .env, and bundled OBS config.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
echo.
pause
