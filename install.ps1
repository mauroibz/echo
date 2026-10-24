# Echo installer for Windows. Installs into this clone (.venv) and your user profile only; no
# administrator rights needed.
# Usage: .\install.ps1 [-WithTranscription [-Compute cuda|cpu]] [-WithoutTranscription]
#   -WithTranscription alone picks cuda for an NVIDIA GPU, cpu otherwise.
param(
    [switch]$WithTranscription,
    [ValidateSet("cuda", "cpu")][string]$Compute = "",
    [switch]$WithoutTranscription
)
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$profileFile = Join-Path $root ".install-profile"
$binDir = Join-Path $env:LOCALAPPDATA "Echo\bin"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"

function Say($text) { Write-Host $text -ForegroundColor Cyan }

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Need($command, $wingetId, $what) {
    if (Get-Command $command -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Echo needs $what. Install it (winget install $wingetId), then run this again."
    }
    Say "Installing $what with winget"
    winget install --id $wingetId --exact --scope user --accept-source-agreements --accept-package-agreements
    Refresh-Path
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$what was installed but is not on PATH yet. Open a new terminal and run this again."
    }
}

# ---- profile ------------------------------------------------------------------------------------
$installProfile = ""
if (Test-Path $profileFile) { $installProfile = (Get-Content $profileFile -Raw).Trim() }
if ($installProfile -eq "full") { $installProfile = "cuda" }
if ($WithoutTranscription) { $installProfile = "base" }
if ($WithTranscription) {
    if ($Compute) {
        $installProfile = $Compute
    } elseif (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $installProfile = "cuda"
        Say "Found an NVIDIA GPU: installing transcription for CUDA."
    } else {
        $installProfile = "cpu"
        Say "No NVIDIA GPU found: transcription will run on the processor (slower)."
    }
    if (-not $Compute) { Write-Host "To choose otherwise: .\install.ps1 -WithTranscription -Compute cuda|cpu" }
}
if (-not $installProfile) { $installProfile = "base" }

# ---- tools --------------------------------------------------------------------------------------
Need "uv" "astral-sh.uv" "uv (it installs Echo's own Python)"
Need "ffmpeg" "Gyan.FFmpeg" "ffmpeg"

# ---- environment --------------------------------------------------------------------------------
Say "Installing Echo ($installProfile profile) into $root\.venv"
Push-Location $root
try {
    uv python install --quiet (Get-Content (Join-Path $root ".python-version") -Raw).Trim()
    if ($installProfile -eq "base") {
        uv sync --locked --no-dev
    } else {
        uv sync --locked --no-dev --extra $installProfile
    }
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
} finally {
    Pop-Location
}
Set-Content -Path $profileFile -Value $installProfile

$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"
$launcher = Join-Path $root "bin\echo-app.pyw"
$icon = Join-Path $root "data\echo-app.ico"

# ---- Start Menu entry ---------------------------------------------------------------------------
Say "Adding the Start Menu entry, the echo-app command and Open with Echo"
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $startMenu "Echo.lnk"))
$lnk.TargetPath = $pythonw
$lnk.Arguments = "-P `"$launcher`""
$lnk.WorkingDirectory = $root
$lnk.IconLocation = $icon
$lnk.Description = "Record and transcribe audio"
$lnk.Save()

# ---- echo-app on PATH ---------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Set-Content -Path (Join-Path $binDir "echo-app.cmd") -Encoding ASCII -Value "@`"$python`" -P `"$launcher`" %*"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $binDir) {
    [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $binDir), "User")
}

# ---- Open with Echo -----------------------------------------------------------------------------
$progId = "HKCU:\Software\Classes\Echo.Audio"
New-Item -Force -Path "$progId\shell\open\command" | Out-Null
Set-ItemProperty -Path $progId -Name "(default)" -Value "Audio for Echo"
Set-ItemProperty -Path "$progId\shell\open\command" -Name "(default)" -Value "`"$pythonw`" -P `"$launcher`" `"%1`""
New-Item -Force -Path "$progId\DefaultIcon" | Out-Null
Set-ItemProperty -Path "$progId\DefaultIcon" -Name "(default)" -Value $icon
foreach ($ext in ".flac", ".opus", ".m4a", ".mp3", ".ogg", ".wav") {
    $key = "HKCU:\Software\Classes\$ext\OpenWithProgids"
    New-Item -Force -Path $key | Out-Null
    New-ItemProperty -Force -Path $key -Name "Echo.Audio" -Value "" -PropertyType String | Out-Null
}

Write-Host ""
& $python -P $launcher doctor --no-gpu
Write-Host ""
Say "Done. Open Echo from the Start Menu, or run echo-app in a new terminal."
