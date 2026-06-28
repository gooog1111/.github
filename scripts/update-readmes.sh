#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install requests deep-translator

: "${GITHUB_REPOSITORY_OWNER:=gooog1111}"
export GITHUB_REPOSITORY_OWNER

python scripts/update_all_readmes.py
