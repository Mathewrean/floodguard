#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env file is required for deployment. Copy .env.example and fill in secrets."
  exit 1
fi

set -a
source .env
set +a

IMAGE_NAME="floodguard:latest"
NETWORK_NAME="floodguard_net"
DB_CONTAINER="floodguard_db"
REDIS_CONTAINER="floodguard_redis"
WEB_CONTAINER="floodguard_web"
CELERY_CONTAINER="floodguard_celery"
CELERY_BEAT_CONTAINER="floodguard_celery_beat"

function ensure_network() {
  if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    docker network create "$NETWORK_NAME"
  fi
}

function recreate_container() {
  local name="$1"
  if docker ps -a --format '{{.Names}}' | grep -xq "$name"; then
    docker rm -f "$name"
  fi
}

function wait_for_postgres() {
  echo "Waiting for PostgreSQL..."
  for i in {1..30}; do
    if docker exec "$DB_CONTAINER" pg_isready -U "${DB_USER:-postgres}" >/dev/null 2>&1; then
      echo "PostgreSQL is ready."
      return
    fi
    sleep 2
  done
  echo "PostgreSQL did not become ready in time." >&2
  exit 1
}

function wait_for_redis() {
  echo "Waiting for Redis..."
  for i in {1..30}; do
    if docker exec "$REDIS_CONTAINER" redis-cli ping >/dev/null 2>&1; then
      echo "Redis is ready."
      return
    fi
    sleep 2
  done
  echo "Redis did not become ready in time." >&2
  exit 1
}

# Build the app image
docker build -t "$IMAGE_NAME" .

ensure_network

recreate_container "$DB_CONTAINER"
recreate_container "$REDIS_CONTAINER"
recreate_container "$WEB_CONTAINER"
recreate_container "$CELERY_CONTAINER"
recreate_container "$CELERY_BEAT_CONTAINER"

# Start PostgreSQL
docker run -d --name "$DB_CONTAINER" --network "$NETWORK_NAME" \
  -e POSTGRES_DB="${DB_NAME:-floodguard}" \
  -e POSTGRES_USER="${DB_USER:-postgres}" \
  -e POSTGRES_PASSWORD="${DB_PASSWORD:-postgres}" \
  -v "$ROOT_DIR/postgres_data:/var/lib/postgresql/data" \
  postgis/postgis:15-3.3

# Start Redis
docker run -d --name "$REDIS_CONTAINER" --network "$NETWORK_NAME" \
  -v "$ROOT_DIR/redis_data:/data" \
  redis:7-alpine

wait_for_postgres
wait_for_redis

# Run database migrations and collect static assets
docker run --rm --network "$NETWORK_NAME" --env-file .env "$IMAGE_NAME" python manage.py migrate --noinput

docker run --rm --network "$NETWORK_NAME" --env-file .env "$IMAGE_NAME" python manage.py collectstatic --noinput

# Start the web service
docker run -d --name "$WEB_CONTAINER" --network "$NETWORK_NAME" \
  --env-file .env -p 8000:8000 "$IMAGE_NAME"

# Start Celery workers
docker run -d --name "$CELERY_CONTAINER" --network "$NETWORK_NAME" \
  --env-file .env "$IMAGE_NAME" celery -A floodguard worker -l info

# Start Celery beat
docker run -d --name "$CELERY_BEAT_CONTAINER" --network "$NETWORK_NAME" \
  --env-file .env "$IMAGE_NAME" celery -A floodguard beat -l info

cat <<MSG
Deployment complete.
App should be available at http://localhost:8000
To stop and remove containers:
  docker rm -f $WEB_CONTAINER $CELERY_CONTAINER $CELERY_BEAT_CONTAINER $DB_CONTAINER $REDIS_CONTAINER
MSG
