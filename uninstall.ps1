# QA Assistant - undo what setup.ps1 created, to free space and leave the machine tidy.
# Run via uninstall.bat (double-click). It does NOT touch the cloned source code or ui/dist.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Info($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host "    $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "    $m" -ForegroundColor Yellow }
function Ask($m)   { return ((Read-Host "    $m (y/N)").Trim().ToLower() -eq 'y') }

Write-Host 'This removes the virtual environment, .env, and the QA-Assistant OBS config' -ForegroundColor Yellow
Write-Host 'that setup created. Your source code and ui/dist are left intact.' -ForegroundColor Yellow
if (-not (Ask 'Continue?')) { Write-Host 'Cancelled.'; return }

# ---------- 1. venv (this is where ffmpeg + all python deps live - the bulk of the space) ----------
$venv = Join-Path $root 'backend\.venv'
if (Test-Path $venv) {
    Info 'Removing backend\.venv (Python deps + bundled ffmpeg)...'
    Remove-Item $venv -Recurse -Force
    Ok 'Virtual environment removed.'
} else { Ok 'No virtual environment found.' }

# ---------- 2. .env (contains your API keys) ----------
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    Info 'Removing .env (your API keys)...'
    Remove-Item $envFile -Force
    Ok '.env removed.'
}

# ---------- 3. __pycache__ + obs-path.txt (both created by setup, not in a fresh clone) ----------
Get-ChildItem -Path (Join-Path $root 'backend') -Filter '__pycache__' -Recurse -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
$obsPathTxt = Join-Path $root 'obs-path.txt'
if (Test-Path $obsPathTxt) { Remove-Item $obsPathTxt -Force; Ok 'obs-path.txt removed.' }

# ---------- 4. OBS config (profile + scene, restore the WebSocket config) ----------
$obsDir = Join-Path $env:APPDATA 'obs-studio'
if (Test-Path $obsDir) {
    if (Get-Process obs64, obs -ErrorAction SilentlyContinue) {
        Warn 'OBS is running - close it and re-run uninstall.bat to remove the OBS config.'
    } else {
        Info 'Removing the QA-Assistant OBS profile + scene collection...'
        $prof  = Join-Path $obsDir 'basic\profiles\QA-Assistant'
        $scene = Join-Path $obsDir 'basic\scenes\QA-Assistant.json'
        if (Test-Path $prof)  { Remove-Item $prof -Recurse -Force }
        if (Test-Path $scene) { Remove-Item $scene -Force }
        # restore the original WebSocket config we backed up (if any)
        $wsFile = Join-Path $obsDir 'plugin_config\obs-websocket\config.json'
        $wsBak  = "$wsFile.bak"
        if (Test-Path $wsBak) {
            Move-Item $wsBak $wsFile -Force
            Ok 'OBS profile/scene removed; original WebSocket config restored.'
        } else {
            Ok 'OBS profile/scene removed. (No WebSocket backup existed; config.json left as-is.)'
        }
    }
} else { Ok 'No OBS config folder found.' }

# ---------- 5. Optional extras (prompted - may be data you want to keep) ----------
$nm = Join-Path $root 'ui\node_modules'
if (Test-Path $nm) {
    if (Ask 'Remove ui\node_modules too? (only present if the UI was built locally)') {
        Remove-Item $nm -Recurse -Force; Ok 'ui\node_modules removed.'
    }
}

$sessions = Join-Path $root 'sessions'
if (Test-Path $sessions) {
    Warn 'sessions\ holds recorded bug clips/screenshots/drafts - this may be unpushed QA work.'
    if (Ask 'Delete the sessions\ folder?') {
        Remove-Item $sessions -Recurse -Force; Ok 'sessions\ deleted.'
    } else { Ok 'sessions\ kept.' }
}

if (Get-Command winget -ErrorAction SilentlyContinue) {
    if (Ask 'Uninstall Python via winget? (skip if you had Python before, or use it for other things)') {
        winget uninstall -e --id Python.Python.3.12
    }
    if (Ask 'Uninstall OBS Studio + ALL its config via winget? (skip if you use OBS for other things)') {
        if (Get-Process obs64, obs -ErrorAction SilentlyContinue) {
            Warn 'OBS is running - close it first, then re-run uninstall.bat.'
        } else {
            winget uninstall -e --id OBSProject.OBSStudio
            # winget leaves %APPDATA%\obs-studio behind - remove it for a clean machine
            if (Test-Path $obsDir) { Remove-Item $obsDir -Recurse -Force; Ok 'OBS config folder removed.' }
        }
    }
}

Write-Host ''
Info 'Uninstall complete.'
Write-Host '  To use QA Assistant again later, just run setup.bat.'
