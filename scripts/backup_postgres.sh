#!/usr/bin/env bash
set -euo pipefail

# FloodGuard PostgreSQL backup script
# Requires pg_dump and database credentials (uses .env via environment)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/floodguard_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# Load environment from .env if present
set -a
[[ -f .env ]] && source .env
set +a

DB_NAME="${DB_NAME:-floodguard}"
DB_USER="${DB_USER:-$(whoami)}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

echo "Backing up database '$DB_NAME' from $DB_HOST:$DB_PORT..."

pg_dump \
  --host="$DB_HOST" \
  --port="$DB_PORT" \
  --username="$DB_USER" \
  --format=plain \
  --no-owner \
  --no-acl \
  "$DB_NAME" \
  | gzip > "$BACKUP_FILE"

echo "Backup saved to: $BACKUP_FILE"

# Remove old backups beyond retention
find "$BACKUP_DIR" -name 'floodguard_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "Old backups (> $RETENTION_DAYS days) removed."
exit 0
