param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/bootstrap.ps1 -Research -Dev first.' }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe scripts/protect_study.py check --manifest docs/study_integrity.json
    if ($LASTEXITCODE -ne 0) { throw 'Protected study verification failed.' }
    & $pythonExe -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff lint failed.' }
    & $pythonExe -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff format check failed.' }
    New-Item -ItemType Directory -Path output -Force | Out-Null
    $testTemp = 'output/verify-runs/' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '/pytest'
    New-Item -ItemType Directory -Path (Split-Path -Parent $testTemp) -Force | Out-Null
    & $pythonExe -m pytest -p no:cacheprovider "--basetemp=$testTemp" --junitxml=output/junit.xml
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
} finally { Pop-Location }
