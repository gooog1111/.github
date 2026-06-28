#!/usr/bin/env bash
set -euo pipefail

cd /srv/github/.github
git pull --ff-only
bash scripts/install-github-actions-cockpit.sh
