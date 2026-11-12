$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $env:RUNNER_TEMP ('gpu-live-package-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testRoot | Out-Null
$env:GPU_LIVE_GRAPHS_DATA_DIR = Join-Path $testRoot 'user-data'
Push-Location -LiteralPath $projectRoot
try {
    $appVersion = python -c "from version import VERSION; print(VERSION)"
    $report = Join-Path $testRoot 'portable-test.json'
    $exe = Join-Path $projectRoot 'dist/GPU-Live-Graphs/GPU-Live-Graphs.exe'
    $process = Start-Process -FilePath $exe -ArgumentList @('--self-test', ('"' + $report + '"')) -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(120000)) { $process.Kill(); throw 'Frozen self-test timed out.' }
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $report)) { throw 'Frozen self-test failed.' }
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $result.success) { throw $result.error }
    Get-Content -LiteralPath $report
    # Install only the freshly built artifact into an isolated test directory.
    $installDir = Join-Path $testRoot 'installed'
    $installer = Join-Path $projectRoot "dist/GPU-Live-Graphs-$appVersion-Setup.exe"
    $setup = Start-Process -FilePath $installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="' + $installDir + '"')) -Wait -PassThru -WindowStyle Hidden
    if ($setup.ExitCode -ne 0) { throw 'Installer smoke test failed.' }
    $installedExe = Join-Path $installDir 'GPU-Live-Graphs.exe'
    $installedReport = Join-Path $testRoot 'installed-test.json'
    $process = Start-Process -FilePath $installedExe -ArgumentList @('--self-test', ('"' + $installedReport + '"')) -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(120000)) { $process.Kill(); throw 'Installed self-test timed out.' }
    if ($process.ExitCode -ne 0) { throw 'Installed application failed.' }
    $uninstaller = Join-Path $installDir 'unins000.exe'
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -Wait -PassThru -WindowStyle Hidden
    if ($uninstall.ExitCode -ne 0) { throw 'Uninstaller failed.' }
    if (Test-Path -LiteralPath $installedExe) { throw 'Uninstaller left the app executable behind.' }
    if (-not (Test-Path -LiteralPath $env:GPU_LIVE_GRAPHS_DATA_DIR)) { throw 'Uninstaller removed user data.' }
    Copy-Item -LiteralPath $report,$installedReport -Destination dist
    Write-Output 'Portable, install, installed launch, and uninstall checks passed.'
} finally {
    Pop-Location
}
