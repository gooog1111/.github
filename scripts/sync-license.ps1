$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install requests

if (-not $env:GITHUB_REPOSITORY_OWNER) {
  $env:GITHUB_REPOSITORY_OWNER = "gooog1111"
}
if (-not $env:SOURCE_FILE) {
  $env:SOURCE_FILE = "LICENSE.md"
}
if (-not $env:TARGET_FILE) {
  $env:TARGET_FILE = "LICENSE.md"
}

& ".\.venv\Scripts\python.exe" scripts\sync_license.py
