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
function Resolve-Python {
    # bare 'python' first; if missing, refresh PATH from registry (winget installs don't show up
    # in the current session) and retry; finally fall back to the default per-user install location.
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $env:Path = ([Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                 [Environment]::GetEnvironmentVariable('Path','User'))
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $guess = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if ($guess) { return $guess.FullName }
    return $null
}
$pyExe = Resolve-Python
if (-not $pyExe) {
    Warn 'Python not found - installing via winget...'
    winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget failed to install Python (exit $LASTEXITCODE). Install Python 3.10+ manually, then run setup.bat again." }
    $pyExe = Resolve-Python
    if (-not $pyExe) { throw 'Python installed but could not be located. Close this window and run setup.bat again.' }
}
Ok ("Python: " + (& $pyExe --version))

# ---------- 2. venv + backend deps ----------
$venv = Join-Path $root 'backend\.venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Info 'Creating virtual environment (backend\.venv)...'
    & $pyExe -m venv $venv
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
    Warn "OBS does not appear to be installed (no config folder at $obsDir)."
    # version pinned to 32.1.2 so it matches the bundled profile/scene (winget 'latest' could drift)
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info 'Installing OBS Studio 32.1.2 via winget...'
        winget install -e --id OBSProject.OBSStudio --version 32.1.2 --accept-source-agreements --accept-package-agreements
        # winget is a native exe - $ErrorActionPreference doesn't catch its exit code, so check manually
        if ($LASTEXITCODE -ne 0) {
            throw "winget failed to install OBS (exit $LASTEXITCODE). If it said 'files in use', close OBS/installer or reboot, then run setup.bat again."
        }
        # the copy steps below create %APPDATA%\obs-studio themselves, so no need to launch OBS first
        New-Item -ItemType Directory -Force -Path $obsDir | Out-Null
    } else {
        Write-Host '    winget unavailable. Install OBS 32.1.2 manually:' -ForegroundColor Yellow
        Write-Host '    https://cdn-fastly.obsproject.com/downloads/OBS-Studio-32.1.2-Windows-x64-Installer.exe' -ForegroundColor Cyan
        $obsDir = Read-Host '    Then enter your OBS config folder path, or press Enter to exit'
        if (-not $obsDir) { return }
        if (-not (Test-Path $obsDir)) { throw "OBS folder not found: $obsDir" }
    }
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

# ---------- 6. OBS install path (used by run.bat to auto-launch OBS) ----------
Info 'Resolving OBS install path...'
$obsInstall = Join-Path $env:ProgramFiles 'obs-studio'
if (-not (Test-Path (Join-Path $obsInstall 'bin\64bit\obs64.exe'))) {
    Warn "OBS not found at $obsInstall."
    $obsInstall = Read-Host '    Enter your OBS install folder (the one containing bin\64bit\obs64.exe)'
    if (-not (Test-Path (Join-Path $obsInstall 'bin\64bit\obs64.exe'))) {
        throw "obs64.exe not found under $obsInstall\bin\64bit"
    }
}
Set-Content -Path (Join-Path $root 'obs-path.txt') -Value $obsInstall -Encoding UTF8 -NoNewline
Ok "OBS install path saved: $obsInstall"

Write-Host ''
Info 'Setup complete. Next steps - run run.bat (asks for admin - needed for hotkeys). It will:'
Write-Host '  1. Open OBS with the QA-Assistant profile + scene (replay buffer NOT started automatically).'
Write-Host '  2. Start the QA Assistant window.'
Write-Host '  3. Open the browser at http://localhost:8000'
Write-Host ''
Write-Host '  One-time only: with Roblox open, in OBS double-click the "Window Capture" source and pick'
Write-Host '  the Roblox window. (Use windowed/borderless mode. Do NOT use Game Capture - Byfron blocks it.)'
