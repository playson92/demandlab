param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    # Install only into this project's environment; never change global Python configuration.
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        & $uvCommand.Source sync --frozen --extra dev --python 3.12
    } else {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if (-not $launcher) { throw 'Install Python 3.12 (with py launcher) or uv, then rerun bootstrap.ps1.' }
        $pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $pythonExe)) {
            & $launcher.Source -3.12 -m venv (Join-Path $projectRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Creating Python 3.12 environment failed.' }
        }
        & $pythonExe -m pip install 'uv==0.13.0'
        if ($LASTEXITCODE -ne 0) { throw 'Installing uv failed.' }
        & $pythonExe -m uv sync --frozen --extra dev --python 3.12
    }
    if ($LASTEXITCODE -ne 0) { throw 'Locked environment installation failed.' }
    Write-Host 'Environment ready. Run .\scripts\run_app.ps1'
} finally { Pop-Location }
