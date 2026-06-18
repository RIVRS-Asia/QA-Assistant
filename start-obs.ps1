# Launch OBS pre-loaded with the QA-Assistant profile + scene collection and the
# replay buffer already running, so the user skips the manual Profile/Scene picking.
# No-op (with a warning) if OBS isn't installed or is already running.
$ErrorActionPreference = 'Stop'

if (Get-Process obs64, obs -ErrorAction SilentlyContinue) {
    Write-Host "    OBS already running - leaving it as is." -ForegroundColor Yellow
    return
}

# Find obs64.exe: default install dir, then the registry uninstall key as fallback.
$exe = "$env:ProgramFiles\obs-studio\bin\64bit\obs64.exe"
if (-not (Test-Path $exe)) {
    $key = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\OBS Studio' -ErrorAction SilentlyContinue
    if ($key.InstallLocation) { $exe = Join-Path $key.InstallLocation 'bin\64bit\obs64.exe' }
}
if (-not (Test-Path $exe)) {
    Write-Host "    OBS not found - install OBS 32.1.2 and run setup.bat. Skipping auto-launch." -ForegroundColor Yellow
    return
}

# OBS requires its bin\64bit as the working directory.
$wd = Split-Path $exe
$obsArgs = @(
    '--profile', 'QA-Assistant',
    '--collection', 'QA-Assistant'
)
Start-Process -FilePath $exe -ArgumentList $obsArgs -WorkingDirectory $wd
Write-Host "    OBS launched (profile + scene QA-Assistant, replay buffer started)." -ForegroundColor Green
