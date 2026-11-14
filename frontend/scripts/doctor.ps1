param([string]$Python = '')
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $Root '.venv/Scripts/python.exe' }
& $Python (Join-Path $PSScriptRoot 'doctor.py')
exit $LASTEXITCODE
