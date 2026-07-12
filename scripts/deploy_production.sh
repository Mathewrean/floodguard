#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env file is required for deployment. Copy .env.example and fill in secrets."
  exit 1
fi

function load_env() {
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line%%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    export "$key=$value"
  done < .env
}

load_env

IMAGE_NAME="floodguard:latest"
NETWORK_NAME="floodguard_net"
DB_CONTAINER="floodguard_db"
REDIS_CONTAINER="floodguard_redis"
WEB_CONTAINER="floodguard_web"
CELERY_CONTAINER="floodguard_celery"
CELERY_BEAT_CONTAINER="floodguard_celery_beat"
SYSTEM_SERVICES=false
DOCKER_CMD="docker"

function print_usage() {
  cat <<EOF
Usage: $0 [--use-system-services] [--help]

Options:
  --use-system-services   Use host PostgreSQL/PostGIS and Redis instead of containerized DB/Redis.
  --help                  Show this help message.
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --use-system-services)
      SYSTEM_SERVICES=true
      shift
      ;;
    -h|--help)
      print_usage
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_usage
      ;;
  esac
done

function require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command '$1' is not installed."
    exit 1
  fi
}

function check_docker_daemon() {
  if docker info >/dev/null 2>&1; then
    DOCKER_CMD="docker"
    return
  fi

  if [[ -n "${DOCKER_HOST:-}" ]]; then
    if DOCKER_HOST=unix:///var/run/docker.sock docker info >/dev/null 2>&1; then
      export DOCKER_HOST=unix:///var/run/docker.sock
      DOCKER_CMD="docker"
      return
    fi
  fi

  if sudo docker info >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
    return
  fi

  echo "Cannot connect to the Docker daemon. Please ensure Docker is installed and running."
  echo "If you are using Podman, start the Podman service or configure Docker CLI compatibility."
  exit 1
}

function ensure_network() {
  if ! $DOCKER_CMD network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    $DOCKER_CMD network create "$NETWORK_NAME"
  fi
}

function recreate_container() {
  local name="$1"
  if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -xq "$name"; then
    $DOCKER_CMD rm -f "$name"
  fi
}

function wait_for_postgres_container() {
  echo "Waiting for PostgreSQL container..."
  for i in {1..30}; do
    if $DOCKER_CMD exec "$DB_CONTAINER" pg_isready -U "${DB_USER:-postgres}" >/dev/null 2>&1; then
      echo "PostgreSQL is ready."
      return
    fi
    sleep 2
  done
  echo "PostgreSQL did not become ready in time." >&2
  exit 1
}

function wait_for_redis_container() {
  echo "Waiting for Redis container..."
  for i in {1..30}; do
    if $DOCKER_CMD exec "$REDIS_CONTAINER" redis-cli ping >/dev/null 2>&1; then
      echo "Redis is ready."
      return
    fi
    sleep 2
  done
  echo "Redis did not become ready in time." >&2
  exit 1
}

function wait_for_postgres_system() {
  echo "Waiting for system PostgreSQL..."
  for i in {1..30}; do
    if PGPASSWORD="${DB_PASSWORD:-}" psql -h "${DB_HOST:-127.0.0.1}" -U "${DB_USER:-postgres}" -d postgres -c '\q' >/dev/null 2>&1; then
      echo "System PostgreSQL is ready."
      return
    fi
    sleep 2
  done
  echo "System PostgreSQL did not become ready in time." >&2
  exit 1
}

function wait_for_redis_system() {
  echo "Waiting for system Redis..."
  for i in {1..30}; do
    if redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
      echo "System Redis is ready."
      return
    fi
    sleep 2
  done
  echo "System Redis did not become ready in time." >&2
  exit 1
}

function install_system_package() {
  local package="$1"
  if command -v apt-get >/dev/null 2>&1; then
    echo "Installing $package..."
    sudo apt-get update
    sudo apt-get install -y "$package"
  else
    echo "Automatic installation is only supported on Debian-based systems. Please install $package manually." >&2
    exit 1
  fi
}

function ensure_system_postgres() {
  if ! command -v psql >/dev/null 2>&1; then
    install_system_package postgresql
    install_system_package postgresql-contrib
    install_system_package postgis
  fi

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now postgresql
  else
    sudo service postgresql start || true
  fi
}

function ensure_system_redis() {
  if ! command -v redis-cli >/dev/null 2>&1; then
    install_system_package redis-server
  fi

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now redis-server
  else
    sudo service redis-server start || true
  fi
}

function ensure_system_database() {
  echo "Creating system database and PostGIS extension if needed..."

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
    sudo -u postgres psql -c "CREATE ROLE \"${DB_USER}\" WITH LOGIN PASSWORD '${DB_PASSWORD}';"
  fi

  if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
    sudo -u postgres psql -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\";"
  fi

  sudo -u postgres psql -d "${DB_NAME}" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
}

function run_migrations_and_collectstatic() {
  local network_flags=()
  local extra_env=()
  if [[ "$SYSTEM_SERVICES" == true ]]; then
    network_flags+=(--network host)
  else
    network_flags+=(--network "$NETWORK_NAME")
    extra_env+=(--env "DB_HOST=$DB_CONTAINER")
    extra_env+=(--env "DB_PORT=${DB_PORT:-5432}")
    extra_env+=(--env "DB_NAME=${DB_NAME:-floodguard}")
    extra_env+=(--env "DB_USER=${DB_USER:-postgres}")
    extra_env+=(--env "DB_PASSWORD=${DB_PASSWORD:-postgres}")
    extra_env+=(--env "DATABASE_URL=postgres://${DB_USER:-postgres}:${DB_PASSWORD:-postgres}@${DB_CONTAINER}:${DB_PORT:-5432}/${DB_NAME:-floodguard}")
    extra_env+=(--env "REDIS_HOST=$REDIS_CONTAINER")
    extra_env+=(--env "REDIS_PORT=6379")
    extra_env+=(--env "REDIS_URL=redis://${REDIS_CONTAINER}:6379/0")
  fi

  $DOCKER_CMD run --rm "${network_flags[@]}" --env-file .env "${extra_env[@]}" "$IMAGE_NAME" python manage.py migrate --noinput
  $DOCKER_CMD run --rm "${network_flags[@]}" --env-file .env "${extra_env[@]}" "$IMAGE_NAME" python manage.py collectstatic --noinput
}

function run_containerized_services() {
  ensure_network

  recreate_container "$DB_CONTAINER"
  recreate_container "$REDIS_CONTAINER"
  recreate_container "$WEB_CONTAINER"
  recreate_container "$CELERY_CONTAINER"
  recreate_container "$CELERY_BEAT_CONTAINER"

  $DOCKER_CMD run -d --name "$DB_CONTAINER" --network "$NETWORK_NAME" \
    -e POSTGRES_DB="${DB_NAME:-floodguard}" \
    -e POSTGRES_USER="${DB_USER:-postgres}" \
    -e POSTGRES_PASSWORD="${DB_PASSWORD:-postgres}" \
    -v "$ROOT_DIR/postgres_data:/var/lib/postgresql/data" \
    postgis/postgis:15-3.3

  $DOCKER_CMD run -d --name "$REDIS_CONTAINER" --network "$NETWORK_NAME" \
    -v "$ROOT_DIR/redis_data:/data" \
    redis:7-alpine

  wait_for_postgres_container
  wait_for_redis_container

  run_migrations_and_collectstatic

  $DOCKER_CMD run -d --name "$WEB_CONTAINER" --network "$NETWORK_NAME" \
    --env-file .env \
    -e "DB_HOST=$DB_CONTAINER" \
    -e "DB_PORT=${DB_PORT:-5432}" \
    -e "DB_NAME=${DB_NAME:-floodguard}" \
    -e "DB_USER=${DB_USER:-postgres}" \
    -e "DB_PASSWORD=${DB_PASSWORD:-postgres}" \
    -e "DATABASE_URL=postgres://${DB_USER:-postgres}:${DB_PASSWORD:-postgres}@${DB_CONTAINER}:${DB_PORT:-5432}/${DB_NAME:-floodguard}" \
    -e "REDIS_HOST=$REDIS_CONTAINER" \
    -e "REDIS_PORT=6379" \
    -e "REDIS_URL=redis://${REDIS_CONTAINER}:6379/0" \
    -p 8000:8000 "$IMAGE_NAME"

  $DOCKER_CMD run -d --name "$CELERY_CONTAINER" --network "$NETWORK_NAME" \
    --env-file .env \
    -e "DB_HOST=$DB_CONTAINER" \
    -e "DB_PORT=${DB_PORT:-5432}" \
    -e "DB_NAME=${DB_NAME:-floodguard}" \
    -e "DB_USER=${DB_USER:-postgres}" \
    -e "DB_PASSWORD=${DB_PASSWORD:-postgres}" \
    -e "DATABASE_URL=postgres://${DB_USER:-postgres}:${DB_PASSWORD:-postgres}@${DB_CONTAINER}:${DB_PORT:-5432}/${DB_NAME:-floodguard}" \
    -e "REDIS_HOST=$REDIS_CONTAINER" \
    -e "REDIS_PORT=6379" \
    -e "REDIS_URL=redis://${REDIS_CONTAINER}:6379/0" \
    "$IMAGE_NAME" celery -A floodguard worker -l info

  $DOCKER_CMD run -d --name "$CELERY_BEAT_CONTAINER" --network "$NETWORK_NAME" \
    --env-file .env \
    -e "DB_HOST=$DB_CONTAINER" \
    -e "DB_PORT=${DB_PORT:-5432}" \
    -e "DB_NAME=${DB_NAME:-floodguard}" \
    -e "DB_USER=${DB_USER:-postgres}" \
    -e "DB_PASSWORD=${DB_PASSWORD:-postgres}" \
    -e "DATABASE_URL=postgres://${DB_USER:-postgres}:${DB_PASSWORD:-postgres}@${DB_CONTAINER}:${DB_PORT:-5432}/${DB_NAME:-floodguard}" \
    -e "REDIS_HOST=$REDIS_CONTAINER" \
    -e "REDIS_PORT=6379" \
    -e "REDIS_URL=redis://${REDIS_CONTAINER}:6379/0" \
    "$IMAGE_NAME" celery -A floodguard beat -l info
}

function run_system_services_mode() {
  ensure_system_postgres
  ensure_system_redis
  ensure_system_database
  wait_for_postgres_system
  wait_for_redis_system

  recreate_container "$WEB_CONTAINER"
  recreate_container "$CELERY_CONTAINER"
  recreate_container "$CELERY_BEAT_CONTAINER"

  run_migrations_and_collectstatic

  $DOCKER_CMD run -d --name "$WEB_CONTAINER" --network host --env-file .env "$IMAGE_NAME"
  $DOCKER_CMD run -d --name "$CELERY_CONTAINER" --network host --env-file .env "$IMAGE_NAME" celery -A floodguard worker -l info
  $DOCKER_CMD run -d --name "$CELERY_BEAT_CONTAINER" --network host --env-file .env "$IMAGE_NAME" celery -A floodguard beat -l info
}

require_command docker
require_command python
require_command sudo
check_docker_daemon

$DOCKER_CMD build -t "$IMAGE_NAME" .

if [[ "$SYSTEM_SERVICES" == true ]]; then
  run_system_services_mode
else
  run_containerized_services
fi

cat <<MSG
Deployment complete.
App should be available at http://localhost:8000
To stop and remove containers:
  docker rm -f $WEB_CONTAINER $CELERY_CONTAINER $CELERY_BEAT_CONTAINER

If you used containerized DB/Redis mode:
  docker rm -f $DB_CONTAINER $REDIS_CONTAINER
MSG
