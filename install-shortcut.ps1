#requires -Version 5.1
param([string]$Executable)
$ErrorActionPreference = 'Stop'
if (-not $Executable) {
    $Executable = Join-Path $PSScriptRoot 'CodexProviderSwitcher.exe'
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        $Executable = Join-Path $PSScriptRoot 'dist\CodexProviderSwitcher.exe'
    }
}
$resolvedExe = (Resolve-Path -LiteralPath $Executable).Path
$iconCandidate = Join-Path (Split-Path -Parent $resolvedExe) 'app-icon.ico'
$resolvedIcon = if (Test-Path -LiteralPath $iconCandidate -PathType Leaf) {
    (Resolve-Path -LiteralPath $iconCandidate).Path
} else {
    $resolvedExe
}
$desktopDir = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutName = -join ([char[]](67,111,100,101,120,32,20250,35805,32,80,114,111,118,105,100,101,114,32,20999,25442,24037,20855))
$shortcutPath = Join-Path $desktopDir ($shortcutName + '.lnk')
$wshell = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $shortcutPath) {
    $existing = $wshell.CreateShortcut($shortcutPath)
    if ($existing.TargetPath -and $existing.TargetPath -ne $resolvedExe) {
        throw "A shortcut with this name already points elsewhere: $shortcutPath"
    }
}
$shortcut = $wshell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $resolvedExe
$shortcut.WorkingDirectory = Split-Path -Parent $resolvedExe
$shortcut.IconLocation = "$resolvedIcon,0"
$shortcut.Description = 'Browse Codex conversations and switch their provider while Codex is closed.'
$shortcut.Save()

# Notify Explorer after changing the icon source so it does not retain the
# cached icon associated with an older executable at the same path.
$shellRefresh = Join-Path $env:WINDIR 'System32\ie4uinit.exe'
if (Test-Path -LiteralPath $shellRefresh -PathType Leaf) {
    & $shellRefresh -show
}
Write-Host $shortcutPath
