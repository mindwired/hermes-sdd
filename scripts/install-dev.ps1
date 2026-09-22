$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $HOME ".hermes" }
$PluginTarget = Join-Path $HermesHome "plugins\sdd"
$BackupRoot = Join-Path $HermesHome "plugin-backups\sdd"
$DesktopDir = Join-Path $HermesHome "desktop-plugins\sdd"
$DesktopTarget = Join-Path $DesktopDir "plugin.js"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

New-Item -ItemType Directory -Force -Path (Split-Path $PluginTarget), $DesktopDir | Out-Null
if (Test-Path $PluginTarget) {
    New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
    Move-Item $PluginTarget (Join-Path $BackupRoot "sdd.backup-$Stamp")
}
Copy-Item -Recurse -Force $Root $PluginTarget
Copy-Item -Force (Join-Path $Root "desktop\plugin.js") $DesktopTarget

Write-Host "Hermes SDD development copy installed. Re-run this script after source changes."
Write-Host "  hermes plugins enable sdd"
Write-Host "  hermes gateway restart"
Write-Host "  hermes sdd doctor"
