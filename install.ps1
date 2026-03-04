#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SkillName = "jetbriefcheck"
$InstallDir = Join-Path $HOME ".claude\skills\$SkillName"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Installing $SkillName skill..."

# Create target directory
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# Copy skill files
$Items = @("SKILL.md", "scripts", "references", "core", "requirements.txt", "version.json")
foreach ($item in $Items) {
    $src = Join-Path $ScriptDir $item
    $dst = Join-Path $InstallDir $item
    if (Test-Path $src) {
        if (Test-Path $dst) {
            Remove-Item -Recurse -Force $dst
        }
        Copy-Item -Path $src -Destination $dst -Recurse -Force
        Write-Host "  Copied: $item"
    }
}

Write-Host "Installed to $InstallDir"

# --- Python virtual environment ---
Write-Host ""
Write-Host "Setting up Python virtual environment..."

$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Using uv to create venv..."
    & uv venv $VenvDir --clear
    & uv pip install -r "$InstallDir\requirements.txt" --python $VenvPython
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    Write-Host "Using python3 to create venv..."
    & python3 -m venv $VenvDir --clear
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r "$InstallDir\requirements.txt"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Using python to create venv..."
    & python -m venv $VenvDir --clear
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r "$InstallDir\requirements.txt"
} else {
    Write-Host "ERROR: Neither uv nor python found. Cannot create virtual environment." -ForegroundColor Red
    Write-Host "  Install Python 3 from https://www.python.org/ or uv from https://docs.astral.sh/uv/"
    exit 1
}

Write-Host "Python packages installed."
Write-Host ""
Write-Host "Done."
