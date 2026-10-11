param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$buildOriginalPath = $env:PATH
$pythonExecutable = (Get-Command $Python -ErrorAction Stop).Source
# Codex's document runtimes may prepend Poppler/libheif DLL directories. Their
# ICU DLL shares a name with the Windows system library but has a different ABI.
$env:PATH = @((Split-Path $pythonExecutable), "$env:SystemRoot\System32", $env:SystemRoot,
    "$env:SystemRoot\System32\WindowsPowerShell\v1.0") -join ';'
Push-Location $PSScriptRoot
try {
    $sharedShortcut = Get-Content -LiteralPath 'shortcut-link.txt' -Raw
    if ($sharedShortcut -and $sharedShortcut.Trim()) {
        $sharedShortcut = $sharedShortcut.Trim()
        & $Python verify_shortcut.py --link $sharedShortcut
        if ($LASTEXITCODE -ne 0) { throw 'Shortcut template verification failed; no package was created.' }
    }
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed --name AirBridgeScreenshot --icon assets/app.ico --add-data 'allow_lan.ps1;.' --add-data 'shortcut-link.txt;.' --exclude-module numpy --exclude-module scipy --exclude-module matplotlib --exclude-module pandas app.py
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    $output = Join-Path $PSScriptRoot 'dist/AirBridgeScreenshot'
    & $Python trim_bundle.py $output
    if ($LASTEXITCODE -ne 0) { throw 'Bundle trimming failed.' }
    Copy-Item -LiteralPath LICENSE,QUICK_START.txt,THIRD_PARTY_NOTICES.md -Destination $output
    Copy-Item -LiteralPath third_party -Destination $output -Recurse -Force
    & $Python collect_licenses.py $output
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
    $archive = Join-Path $PSScriptRoot 'dist/AirBridgeScreenshot-0.1.0-preview-windows-x64.zip'
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
    Compress-Archive -LiteralPath $output -DestinationPath $archive -CompressionLevel Optimal
    Get-FileHash -LiteralPath $archive -Algorithm SHA256 | Format-List
    Write-Host "Built: $archive"
} finally { Pop-Location; $env:PATH = $buildOriginalPath }
