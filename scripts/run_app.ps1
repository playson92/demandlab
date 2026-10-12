param([int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/bootstrap.ps1 first.' }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe (Join-Path $projectRoot 'scripts\run_demo.py') --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Streamlit exited with code $LASTEXITCODE" }
} finally { Pop-Location }
