param([int]$Port = 8501)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/bootstrap.ps1 first.' }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port $Port
    if ($LASTEXITCODE -ne 0) { throw "Streamlit exited with code $LASTEXITCODE" }
} finally { Pop-Location }
