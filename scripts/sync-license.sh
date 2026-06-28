#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install requests

: "${GITHUB_REPOSITORY_OWNER:=gooog1111}"
: "${SOURCE_FILE:=LICENSE.md}"
: "${TARGET_FILE:=LICENSE.md}"
export GITHUB_REPOSITORY_OWNER SOURCE_FILE TARGET_FILE

python scripts/sync_license.py
