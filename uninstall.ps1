# Remove Echo's Start Menu entry, command, file associations and environment. Recordings are kept.
# Usage: .\uninstall.ps1 [-Purge]   (-Purge also deletes recordings, settings and logs, after asking)
param([switch]$Purge)
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$binDir = Join-Path $env:LOCALAPPDATA "Echo\bin"

Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Echo.lnk")
Remove-Item -Force -Recurse -ErrorAction SilentlyContinue $binDir
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $kept = ($userPath -split ";") | Where-Object { $_ -and $_ -ne $binDir }
    [Environment]::SetEnvironmentVariable("Path", ($kept -join ";"), "User")
}
Remove-Item -Force -Recurse -ErrorAction SilentlyContinue "HKCU:\Software\Classes\Echo.Audio"
foreach ($ext in ".flac", ".opus", ".m4a", ".mp3", ".ogg", ".wav") {
    Remove-ItemProperty -ErrorAction SilentlyContinue -Path "HKCU:\Software\Classes\$ext\OpenWithProgids" -Name "Echo.Audio"
}
Remove-Item -Force -Recurse -ErrorAction SilentlyContinue (Join-Path $root ".venv"), (Join-Path $root ".install-profile")
Write-Host "Removed the Start Menu entry, the echo-app command, Open with Echo and $root\.venv"

$dataDir = Join-Path $env:USERPROFILE "Documents\Echo"
$settings = Join-Path $env:APPDATA "Echo\settings.toml"
if (Test-Path $settings) {
    $line = Select-String -Path $settings -Pattern '^data_dir = "(.+)"$' | Select-Object -First 1
    if ($line) { $dataDir = $line.Matches[0].Groups[1].Value -replace '\\\\', '\' }
}

if ($Purge) {
    $answer = Read-Host "Delete ALL recordings and transcripts in $dataDir? Type delete to confirm"
    if ($answer -eq "delete") {
        Remove-Item -Force -Recurse -ErrorAction SilentlyContinue $dataDir, (Join-Path $env:APPDATA "Echo"),
            (Join-Path $env:LOCALAPPDATA "Echo")
        Write-Host "Deleted recordings, settings and logs."
    } else {
        Write-Host "Kept your recordings."
    }
} else {
    Write-Host "Your recordings are still in $dataDir"
}
Write-Host "Downloaded models (if any) stay in the Hugging Face cache: $env:USERPROFILE\.cache\huggingface\hub"
