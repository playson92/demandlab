param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/bootstrap.ps1 first.' }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff lint failed.' }
    & $pythonExe -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff format check failed.' }
    New-Item -ItemType Directory -Path output -Force | Out-Null
    & $pythonExe -m pytest -p no:cacheprovider --basetemp=output/pytest --junitxml=output/junit.xml
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
} finally { Pop-Location }
