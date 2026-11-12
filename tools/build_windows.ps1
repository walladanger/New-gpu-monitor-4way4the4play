$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $appVersion = python -c "from version import VERSION; print(VERSION)"
    if ($LASTEXITCODE -ne 0) { throw 'Could not read app version.' }
    # Documented onedir/windowed packaging: https://pyinstaller.org/en/stable/usage.html
    python -m PyInstaller --noconfirm --clean --onedir --windowed --noupx --name GPU-Live-Graphs --specpath build --workpath build/pyinstaller --distpath dist Launch.pyw
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    Copy-Item -LiteralPath LICENSE -Destination dist/GPU-Live-Graphs/LICENSE.txt
    $compiler = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Inno Setup *\ISCC.exe", "$env:ProgramFiles\Inno Setup *\ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $compiler) { throw 'Install Inno Setup 6 or later from jrsoftware.org before building the installer.' }
    & $compiler.FullName "/DMyAppVersion=$appVersion" installer/GPU-Live-Graphs.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    Compress-Archive -Path dist/GPU-Live-Graphs -DestinationPath "dist/GPU-Live-Graphs-$appVersion-Windows-x64.zip" -Force
    Get-ChildItem -Path dist/*.zip, dist/*-Setup.exe | ForEach-Object {
        $digest = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$digest  $($_.Name)"
    } | Set-Content -LiteralPath dist/SHA256SUMS-Windows.txt -Encoding ascii
} finally {
    Pop-Location
}
