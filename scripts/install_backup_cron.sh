#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRON_JOB="0 2 * * * $ROOT_DIR/scripts/backup_postgres.sh >> $ROOT_DIR/backups/backup.log 2>&1"

# Install cron job if not already present
if (crontab -l 2>/dev/null | grep -F "$ROOT_DIR/scripts/backup_postgres.sh" >/dev/null); then
    echo "Cron job already installed."
else
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job installed: daily at 02:00 UTC"
fi
