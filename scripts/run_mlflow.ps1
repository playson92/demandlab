param([int]$Port = 5000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/bootstrap.ps1 first.' }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe scripts/mlflow_ui.py --port $Port
    if ($LASTEXITCODE -ne 0) { throw "MLflow exited with code $LASTEXITCODE" }
} finally { Pop-Location }
