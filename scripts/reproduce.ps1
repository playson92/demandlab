param([string]$SourceFile)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/bootstrap.ps1 first.' }
Push-Location -LiteralPath $projectRoot
try {
    $pipelineArguments = @('-m', 'demandlab', 'reproduce')
    if ($SourceFile) { $pipelineArguments += @('--source-file', $SourceFile) }
    & $pythonExe @pipelineArguments
    if ($LASTEXITCODE -ne 0) { throw "Pipeline exited with code $LASTEXITCODE" }
} finally { Pop-Location }
