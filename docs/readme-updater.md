# README updater

Centralized updater for repository README files.

It updates repositories owned by `gooog1111`:

- root `README.md`
- generated `README.en.md`
- `traffic-views.png`
- missing `resources/header.svg`

The special `.github/profile/README.md` is not updated by this script.

The server also includes a Cockpit page named `GitHub Actions`. It manages
README updates, LICENSE sync, schedules, manual runs, logs, and a JSON action
list for future automations.

## Authentication

Use one of these options:

1. Set `REPO_SYNC_TOKEN` to a token with repository write access.
2. Run `gh auth login`; the script will use `gh auth token` when `REPO_SYNC_TOKEN` is not set.

## Manual Windows Run

From the `.github` repository:

```powershell
.\scripts\update-readmes.ps1
```

## Manual Linux Run

From the `.github` repository:

```bash
bash scripts/update-readmes.sh
```

## Cron Example

```cron
17 4 * * * cd /srv/github/.github && REPO_SYNC_TOKEN=your_token_here bash scripts/update-readmes.sh >> /var/log/readme-updater.log 2>&1
```

## Systemd Service

`/etc/systemd/system/readme-updater.service`:

```ini
[Unit]
Description=Update GitHub repository READMEs

[Service]
Type=oneshot
WorkingDirectory=/srv/github/.github
Environment=GITHUB_REPOSITORY_OWNER=gooog1111
EnvironmentFile=/etc/readme-updater.env
ExecStart=/bin/bash scripts/update-readmes.sh
```

`/etc/systemd/system/readme-updater.timer`:

```ini
[Unit]
Description=Run README updater daily

[Timer]
OnCalendar=*-*-* 04:17:00
Persistent=true

[Install]
WantedBy=timers.target
```

`/etc/readme-updater.env`:

```text
REPO_SYNC_TOKEN=your_token_here
```

Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now readme-updater.timer
```
