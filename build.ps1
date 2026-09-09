#requires -Version 7.0
param([string]$Python = (Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Create .build-venv with a standard CPython runtime and install requirements.txt first. See README.md.'
}
$testRoot = Join-Path $PSScriptRoot '.build-test-tmp'
try {
    & $Python -m pytest -q --basetemp $testRoot -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; packaging stopped.' }
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
$iconSource = Join-Path $PSScriptRoot 'provider_switcher\assets\app-icon.png'
$iconTarget = Join-Path $PSScriptRoot 'provider_switcher\assets\app-icon.ico'
if (-not (Test-Path -LiteralPath $iconTarget -PathType Leaf) -or
    (Get-Item -LiteralPath $iconSource).LastWriteTimeUtc -gt (Get-Item -LiteralPath $iconTarget).LastWriteTimeUtc) {
    & $Python -c 'import PIL'
    if ($LASTEXITCODE -ne 0) {
        throw 'Pillow is required to regenerate app-icon.ico after app-icon.png changes.'
    }
    & $Python tools\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
}
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name CodexProviderSwitcher --icon provider_switcher\assets\app-icon.ico --add-data 'provider_switcher\assets\app-icon.png;provider_switcher\assets' gui_main.py
if ($LASTEXITCODE -ne 0) { throw 'GUI packaging failed.' }
& $Python -m PyInstaller --noconfirm --clean --onefile --console --name codex-provider --icon provider_switcher\assets\app-icon.ico cli_main.py
if ($LASTEXITCODE -ne 0) { throw 'CLI packaging failed.' }
$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) ('codex-provider-smoke-' + [Guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $smokeRoot | Out-Null
    $demoHome = Join-Path $smokeRoot 'demo-home'
    $screenshot = Join-Path $smokeRoot 'gui.png'
    & $Python tools\create_demo.py $demoHome
    if ($LASTEXITCODE -ne 0) { throw 'Smoke-test data generation failed.' }
    $cliJson = & (Join-Path $PSScriptRoot 'dist\codex-provider.exe') --codex-home $demoHome list --include-archived --include-agents --json
    if ($LASTEXITCODE -ne 0 -or ($cliJson | ConvertFrom-Json).threads.Count -ne 4) {
        throw 'Packaged CLI smoke test failed.'
    }
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = Join-Path $PSScriptRoot 'dist\CodexProviderSwitcher.exe'
    $start.UseShellExecute = $false
    [void]$start.ArgumentList.Add('--codex-home')
    [void]$start.ArgumentList.Add($demoHome)
    [void]$start.ArgumentList.Add('--smoke-test')
    [void]$start.ArgumentList.Add($screenshot)
    $process = [Diagnostics.Process]::Start($start)
    if (-not $process.WaitForExit(30000)) {
        $process.Kill($true)
        throw 'Packaged GUI smoke test timed out.'
    }
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $screenshot -PathType Leaf) -or (Get-Item -LiteralPath $screenshot).Length -eq 0) {
        throw 'Packaged GUI smoke test failed.'
    }
}
finally {
    if (Test-Path -LiteralPath $smokeRoot) {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force
    }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination (Join-Path $PSScriptRoot 'dist\使用说明.md')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LICENSE') -Destination (Join-Path $PSScriptRoot 'dist\LICENSE')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'VALIDATION.md') -Destination (Join-Path $PSScriptRoot 'dist\验收报告.md')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-shortcut.ps1') -Destination (Join-Path $PSScriptRoot 'dist\install-shortcut.ps1')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $PSScriptRoot 'dist\THIRD_PARTY_NOTICES.md')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'provider_switcher\assets\app-icon.png') -Destination (Join-Path $PSScriptRoot 'dist\app-icon.png')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'provider_switcher\assets\app-icon.ico') -Destination (Join-Path $PSScriptRoot 'dist\app-icon.ico')
& $Python tools\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
Write-Host 'Build complete. Run install-shortcut.ps1 to create the desktop shortcut.'
