# QA Assistant - one-shot setup for a fresh machine.
# Run via setup.bat (double-click). Does: Python venv + deps, .env (prompts for API keys),
# and copies the bundled OBS profile/scene/websocket config into %APPDATA%\obs-studio.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$OBS_PASSWORD = 'QVjAyEiBfwlfcXBp'   # must match obs-config/obs-websocket-config.json

function Info($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host "    $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "    $m" -ForegroundColor Yellow }

# ---------- 1. Python ----------
Info 'Checking Python...'
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) {
    Warn 'Python not found - installing via winget...'
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    $py = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $py) {
        Warn 'Python installed but not on PATH yet. Close this window and run setup.bat again.'
        return
    }
}
Ok ("Python: " + (python --version))

# ---------- 2. venv + backend deps ----------
$venv = Join-Path $root 'backend\.venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Info 'Creating virtual environment (backend\.venv)...'
    python -m venv $venv
}
Info 'Installing backend dependencies (imageio-ffmpeg bundles ffmpeg, downloaded automatically ~70MB - needs internet)...'
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r (Join-Path $root 'backend\requirements.txt')
Ok 'Backend dependencies installed.'

# ---------- 3. UI build ----------
$dist = Join-Path $root 'ui\dist\index.html'
if (Test-Path $dist) {
    Ok 'UI build (ui\dist) is present - served by the backend at http://localhost:8000'
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Info 'ui\dist missing - building UI with npm...'
    Push-Location (Join-Path $root 'ui'); npm install; npm run build; Pop-Location
} else {
    Warn 'ui\dist is missing and Node/npm is not installed. The delivered repo should include ui\dist.'
}

# ---------- 4. .env (API keys) ----------
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    Ok '.env already exists - leaving it untouched.'
} else {
    Info 'Creating .env - enter at least ONE transcription API key (press Enter to skip a key):'
    $gemini = Read-Host '    GEMINI_API_KEY (recommended)'
    $groq   = Read-Host '    GROQ_API_KEY'
    $openai = Read-Host '    OPENAI_API_KEY'
    if (-not ($gemini -or $groq -or $openai)) {
        throw 'You must provide at least one of GEMINI / GROQ / OPENAI API key.'
    }
    $tpl = Get-Content (Join-Path $root '.env.example') -Raw
    $tpl = $tpl -replace '(?m)^GEMINI_API_KEY=.*$', "GEMINI_API_KEY=$gemini"
    $tpl = $tpl -replace '(?m)^GROQ_API_KEY=.*$',   "GROQ_API_KEY=$groq"
    $tpl = $tpl -replace '(?m)^OPENAI_API_KEY=.*$', "OPENAI_API_KEY=$openai"
    $tpl = $tpl -replace '(?m)^OBS_PASSWORD=.*$',    "OBS_PASSWORD=$OBS_PASSWORD"
    Set-Content -Path $envFile -Value $tpl -Encoding UTF8 -NoNewline
    Ok '.env created (OBS_PASSWORD set to match the bundled OBS config).'
}

# ---------- 5. OBS config ----------
Info 'Setting up OBS config...'
Warn 'Bundled config was made with OBS 32.1.2 - use the same version to avoid compatibility issues.'
$obsDir = Join-Path $env:APPDATA 'obs-studio'
if (-not (Test-Path $obsDir)) {
    Warn "Default OBS folder not found at $obsDir"
    $obsDir = Read-Host '    Enter your OBS config folder path (or run OBS once, then re-run setup)'
    if (-not (Test-Path $obsDir)) { throw "OBS folder not found: $obsDir" }
}
if (Get-Process obs64, obs -ErrorAction SilentlyContinue) {
    throw 'OBS is running. Close OBS completely, then run setup.bat again (OBS overwrites its config on exit).'
}
$src = Join-Path $root 'obs-config'
# profile
$profDst = Join-Path $obsDir 'basic\profiles\QA-Assistant'
New-Item -ItemType Directory -Force -Path $profDst | Out-Null
Copy-Item (Join-Path $src 'profiles\QA-Assistant\*') $profDst -Recurse -Force
# scene collection
$sceneDst = Join-Path $obsDir 'basic\scenes'
New-Item -ItemType Directory -Force -Path $sceneDst | Out-Null
Copy-Item (Join-Path $src 'scenes\QA-Assistant.json') $sceneDst -Force
# websocket config (machine-global) - back up the existing one first
$wsDst = Join-Path $obsDir 'plugin_config\obs-websocket'
New-Item -ItemType Directory -Force -Path $wsDst | Out-Null
$wsFile = Join-Path $wsDst 'config.json'
if (Test-Path $wsFile) { Copy-Item $wsFile "$wsFile.bak" -Force }
Copy-Item (Join-Path $src 'obs-websocket-config.json') $wsFile -Force
Ok 'OBS profile "QA-Assistant", scene collection, and WebSocket config installed.'

Write-Host ''
Info 'Setup complete. Next steps:'
Write-Host '  1. Open OBS once. Top menu: Profile -> QA-Assistant, Scene Collection -> QA-Assistant.'
Write-Host '  2. With Roblox open, double-click the "Window Capture" source and pick the Roblox window.'
Write-Host '     (Use windowed/borderless mode. Do NOT use Game Capture - Byfron blocks it.)'
Write-Host '  3. Close OBS, then run run.bat to start the app (it will ask for admin - needed for hotkeys).'
Write-Host '  4. Browser opens at http://localhost:8000'
