param(
  [ValidateSet('live')][string]$Mode = 'live',
  [string]$Python = '',
  [string]$CaptureDirectory = '\\wsl.localhost\Ubuntu\home\wilson\test_images',
  [ValidateRange(1024,65535)][int]$Port = 3000,
  [ValidateRange(1024,65535)][int]$EdgePort = 8000
)
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..')
try {
  if (-not $Python) { $Python = Join-Path $PWD '.venv/Scripts/python.exe' }
  if (-not (Test-Path -LiteralPath $Python)) { throw 'Create .venv and install apps/edge/requirements.txt first. See README.' }
  if (-not (Test-Path -LiteralPath 'node_modules')) { throw 'Run pnpm install --frozen-lockfile first.' }
  $env:SPACEGIT_MODE = $Mode
  $env:SPACEGIT_CAPTURE_EXPORT_DIR = $CaptureDirectory
  $env:SPACEGIT_POINTDIT_WSL = '1'
  $env:SPACEGIT_LOCAL_SESSION = '1'
  if (-not $env:SPACEGIT_TOKEN) { $env:SPACEGIT_TOKEN = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N') }
  $env:NEXT_TELEMETRY_DISABLED = '1'
  $env:NEXT_PUBLIC_SPACEGIT_EDGE_URL = "http://127.0.0.1:$EdgePort"
  $env:SPACEGIT_EDGE_PORT = "$EdgePort"
  $edge = Start-Process -FilePath $Python -ArgumentList @('-m','uvicorn','spacegit_edge.main:app','--app-dir','apps/edge','--host','127.0.0.1','--port',"$EdgePort",'--no-access-log','--ws-max-size','1024') -WindowStyle Hidden -PassThru
  try {
    $ready = $false
    for ($i=0; $i -lt 30 -and -not $edge.HasExited; $i++) {
      try {
        $status = Invoke-RestMethod "http://127.0.0.1:$EdgePort/health" -TimeoutSec 1
        if ($status.mode -eq $Mode) { $ready = $true; break }
      } catch {}
      Start-Sleep -Milliseconds 250
    }
    if (-not $ready -or $edge.HasExited) { throw "Edge did not start. Check port $EdgePort and Python dependencies. Start uvicorn in a separate terminal for logs." }
    Write-Host "SpaceGit $Mode · http://127.0.0.1:$Port/setup"
    Write-Host "Local operator key (paste in Setup): $env:SPACEGIT_TOKEN"
    pnpm.cmd dev --port $Port
  } finally { if (-not $edge.HasExited) { Stop-Process -Id $edge.Id } }
} finally { Pop-Location }
