$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install requests deep-translator

if (-not $env:GITHUB_REPOSITORY_OWNER) {
  $env:GITHUB_REPOSITORY_OWNER = "gooog1111"
}

& ".\.venv\Scripts\python.exe" scripts\update_all_readmes.py
