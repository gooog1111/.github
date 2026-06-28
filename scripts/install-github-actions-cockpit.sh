#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

sudo install -D -m 0644 systemd/readme-updater.service /etc/systemd/system/readme-updater.service
sudo install -D -m 0644 systemd/readme-updater.timer /etc/systemd/system/readme-updater.timer
sudo install -D -m 0644 systemd/license-sync.service /etc/systemd/system/license-sync.service
sudo install -D -m 0644 systemd/license-sync.timer /etc/systemd/system/license-sync.timer
sudo install -D -m 0644 systemd/github-actions-updater.service /etc/systemd/system/github-actions-updater.service
sudo install -D -m 0644 systemd/github-actions-updater.timer /etc/systemd/system/github-actions-updater.timer

sudo rm -rf /usr/share/cockpit/readme-updater
sudo mkdir -p /usr/share/cockpit/readme-updater
sudo cp -a cockpit/readme-updater/. /usr/share/cockpit/readme-updater/
sudo chown -R root:root /usr/share/cockpit/readme-updater
sudo find /usr/share/cockpit/readme-updater -type d -exec chmod 0755 {} +
sudo find /usr/share/cockpit/readme-updater -type f -exec chmod 0644 {} +

sudo mkdir -p /etc/github-actions-cockpit
if [[ ! -f /etc/github-actions-cockpit/actions.json ]]; then
  sudo install -D -m 0644 cockpit/actions.json /etc/github-actions-cockpit/actions.json
else
  tmp="$(mktemp)"
  sudo python3 - <<'PY' > "$tmp"
import json
from pathlib import Path

default_path = Path("cockpit/actions.json")
config_path = Path("/etc/github-actions-cockpit/actions.json")

defaults = json.loads(default_path.read_text(encoding="utf-8"))
try:
    current = json.loads(config_path.read_text(encoding="utf-8"))
except Exception:
    current = []

if not isinstance(current, list):
    current = []

known = {item.get("id") for item in current if isinstance(item, dict)}
for item in defaults:
    if isinstance(item, dict) and item.get("id") not in known:
        current.append(item)
        known.add(item.get("id"))

print(json.dumps(current, ensure_ascii=False, indent=2))
PY
  sudo install -m 0644 "$tmp" /etc/github-actions-cockpit/actions.json
  rm -f "$tmp"
fi

sudo systemctl daemon-reload
sudo systemctl reload-or-restart cockpit.socket || true
