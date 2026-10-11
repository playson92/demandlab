param([switch]$Research, [switch]$Dev)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $syncArguments = @('sync', '--frozen', '--python', '3.12', '--cache-dir', 'output/uv-cache')
    if ($Research) { $syncArguments += @('--extra', 'research') }
    if ($Dev) { $syncArguments += @('--extra', 'dev') }
    # Install only into this project's environment; never change global Python configuration.
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        & $uvCommand.Source @syncArguments
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
        & $pythonExe -m uv @syncArguments
    }
    if ($LASTEXITCODE -ne 0) { throw 'Locked environment installation failed.' }
    Write-Host 'Environment ready. Run .\scripts\run_app.ps1'
} finally { Pop-Location }
