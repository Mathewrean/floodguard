#!/usr/bin/env bash
set -Eeuo pipefail

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
POSTGRES_CLUSTER="${POSTGRES_CLUSTER:-18 main}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgresql@18-main.service}"
REDIS_LOG="${REDIS_LOG:-/tmp/redis-floodguard.log}"
REDIS_PID="${REDIS_PID:-/tmp/redis-floodguard.pid}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -d "$ROOT_DIR/floodguard_env" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/floodguard_env/bin/activate"
fi

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "ERROR: Required command not found: $1"
        exit 1
    }
}

run_sudo() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

wait_for() {
    local label="$1"
    local command="$2"
    local attempts="${3:-20}"
    local delay="${4:-1}"

    for _ in $(seq 1 "$attempts"); do
        if eval "$command" >/dev/null 2>&1; then
            echo "$label is ready."
            return 0
        fi
        sleep "$delay"
    done

    echo "ERROR: $label did not become ready."
    return 1
}

start_postgres() {
    echo "Checking PostgreSQL..."
    if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        echo "PostgreSQL is already accepting connections."
        return
    fi

    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        echo "Requesting sudo once for PostgreSQL service startup."
        sudo -v
    fi

    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet "$POSTGRES_SERVICE"; then
            echo "$POSTGRES_SERVICE is active."
        else
            echo "Starting $POSTGRES_SERVICE..."
            run_sudo systemctl start "$POSTGRES_SERVICE" || true
        fi
    fi

    if ! pg_isready -h localhost -p 5432 >/dev/null 2>&1 && command -v pg_ctlcluster >/dev/null 2>&1; then
        echo "Starting PostgreSQL cluster: $POSTGRES_CLUSTER..."
        run_sudo pg_ctlcluster $POSTGRES_CLUSTER start || true
    fi

    wait_for "PostgreSQL" "pg_isready -h localhost -p 5432"
}

start_redis() {
    echo "Checking Redis..."
    if redis-cli ping >/dev/null 2>&1; then
        echo "Redis is already running."
        return
    fi

    echo "Starting Redis with direct daemon mode..."
    redis-server --daemonize yes \
        --logfile "$REDIS_LOG" \
        --pidfile "$REDIS_PID"

    wait_for "Redis" "redis-cli ping"
}

echo "Starting FloodGuard development environment..."

need_cmd python
need_cmd pg_isready
need_cmd redis-cli
need_cmd redis-server
need_cmd celery
need_cmd daphne

start_postgres
start_redis

echo "Applying database migrations..."
python manage.py migrate --run-syncdb

echo "Initialising database with real flood data..."
python manage.py init_db --skip-confirmation

echo "Collecting static files for Daphne/Whitenoise..."
python manage.py collectstatic --noinput --clear 2>&1 | tail -3

echo "Starting Celery worker..."
mkdir -p logs
pkill -f "celery -A floodguard worker" 2>/dev/null || true
sleep 1
celery -A floodguard worker --loglevel=warning --detach \
    --logfile=logs/celery.log --pidfile=logs/celery.pid
echo "Celery worker started."

echo ""
echo "========================================"
echo "FloodGuard running at http://$APP_HOST:$APP_PORT"
echo "Local URL: http://127.0.0.1:$APP_PORT"
echo "Admin: http://127.0.0.1:$APP_PORT/admin/"
echo "Credentials: admin / admin123"
echo "========================================"
daphne -b "$APP_HOST" -p "$APP_PORT" floodguard.asgi:application
