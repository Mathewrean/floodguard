#!/bin/bash
BACKUP_DIR="/app/floodguard/backups"
mkdir -p $BACKUP_DIR

# Pull database authentication variables directly from your active .env file
export $(grep -v '^#' /app/floodguard/.env | xargs)

FILENAME="$BACKUP_DIR/floodguard_backup_$(date +%Y%m%d_%H%M%S).sql"

# Dump the core spatial database schemas cleanly using Docker entries configuration
docker exec floodguard-db-1 pg_dump -U ${DB_USER:-postgres} ${DB_NAME:-floodguard} > $FILENAME

# Keep storage optimized by automatically purging historical backups older than 7 days
find $BACKUP_DIR -type f -mtime +7 -name "*.sql" -delete

echo "✓ Database backup successfully saved to: $FILENAME"
