@echo off
REM Start the QA Assistant. Self-elevates to admin so global hotkeys work while the game is focused.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges - needed for global hotkeys...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

setlocal enabledelayedexpansion
where git >nul 2>&1
if %errorlevel% equ 0 (
    for /f %%b in ('git -C "%~dp0." rev-parse --abbrev-ref HEAD 2^>nul') do set _BRANCH=%%b
    if "!_BRANCH!"=="main" (
        git -C "%~dp0." diff --quiet 2>nul && git -C "%~dp0." diff --cached --quiet 2>nul
        if !errorlevel! equ 0 (
            echo [git] main - clean, pulling latest...
            git -C "%~dp0." pull origin main
        ) else (
            echo [git] main - has local changes, running as-is.
        )
    ) else (
        echo [git] branch: !_BRANCH! - running as-is.
    )
) else (
    echo [git] git not found - running as-is. Run setup.bat to install git.
)
endlocal

cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b
)

REM auto-launch OBS with the QA-Assistant profile/scene + replay buffer running
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-obs.ps1"

REM open the browser shortly after the server starts
start "" /min cmd /c "ping -n 3 127.0.0.1 >nul & start http://localhost:8000"

echo Starting QA Assistant on http://localhost:8000  (Ctrl+C to stop)
".venv\Scripts\python.exe" -m uvicorn main:app --port 8000 > "%~dp0run.log" 2>&1
pause
