#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

sudo install -D -m 0644 systemd/readme-updater.service /etc/systemd/system/readme-updater.service
sudo install -D -m 0644 systemd/readme-updater.timer /etc/systemd/system/readme-updater.timer
sudo install -D -m 0644 systemd/license-sync.service /etc/systemd/system/license-sync.service
sudo install -D -m 0644 systemd/license-sync.timer /etc/systemd/system/license-sync.timer

sudo rm -rf /usr/share/cockpit/readme-updater
sudo mkdir -p /usr/share/cockpit/readme-updater
sudo cp -a cockpit/readme-updater/. /usr/share/cockpit/readme-updater/
sudo chown -R root:root /usr/share/cockpit/readme-updater
sudo find /usr/share/cockpit/readme-updater -type d -exec chmod 0755 {} +
sudo find /usr/share/cockpit/readme-updater -type f -exec chmod 0644 {} +

sudo mkdir -p /etc/github-actions-cockpit
if [[ ! -f /etc/github-actions-cockpit/actions.json ]]; then
  sudo install -D -m 0644 cockpit/actions.json /etc/github-actions-cockpit/actions.json
fi

sudo systemctl daemon-reload
sudo systemctl reload-or-restart cockpit.socket || true
