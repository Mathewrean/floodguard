#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/floodguard_env"
PYTHON_BIN="$VENV_DIR/bin/python"
CELERY_BIN="$VENV_DIR/bin/celery"
DAPHNE_BIN="$VENV_DIR/bin/daphne"
LOG_DIR="$ROOT_DIR/logs"
DEPS_MARKER="$VENV_DIR/.deps_synced"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgresql@18-main.service}"
REDIS_LOG="${REDIS_LOG:-/tmp/redis-floodguard.log}"
REDIS_PID="${REDIS_PID:-/tmp/redis-floodguard.pid}"
SYNC_DEPS="${SYNC_DEPS:-auto}"
SEED_DB="${SEED_DB:-1}"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-floodguard.settings}"
export PYTHONUNBUFFERED=1

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not found"; exit 1; }
}

run_sudo() {
    [[ "${EUID:-$(id -u)}" -eq 0 ]] && "$@" || sudo "$@"
}

wait_for() {
    local label="$1" cmd="$2" attempts="${3:-15}" delay="${4:-1}"
    for _ in $(seq 1 "$attempts"); do
        eval "$cmd" >/dev/null 2>&1 && { echo "$label ready."; return 0; }
        sleep "$delay"
    done
    echo "ERROR: $label did not become ready."; return 1
}

ensure_virtualenv() {
    [[ ! -x "$PYTHON_BIN" ]] && { need_cmd python3; python3 -m venv "$VENV_DIR"; }
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
}

sync_dependencies() {
    mkdir -p "$LOG_DIR"
    if [[ "$SYNC_DEPS" == "0" ]]; then
        echo "Skipping dependency sync."; return
    fi
    if [[ "$SYNC_DEPS" == "1" || ! -f "$DEPS_MARKER" || \
          "$ROOT_DIR/requirements.txt" -nt "$DEPS_MARKER" ]]; then
        echo "Syncing dependencies..."
        "$PYTHON_BIN" -m pip install -q --upgrade pip
        "$PYTHON_BIN" -m pip install -q -r "$ROOT_DIR/requirements.txt"
        touch "$DEPS_MARKER"
    else
        echo "Dependencies up to date."
    fi
}

start_postgres() {
    echo "Checking PostgreSQL..."

    # Already accepting connections — nothing to do
    if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
        echo "PostgreSQL already running."; return
    fi

    # Try systemctl first
    if command -v systemctl >/dev/null 2>&1; then
        if ! systemctl is-active --quiet "$POSTGRES_SERVICE"; then
            echo "Starting $POSTGRES_SERVICE..."
            run_sudo systemctl start "$POSTGRES_SERVICE" || true
        fi
    fi

    # Re-check — if still not ready, skip (don't try pg_ctlcluster on running instance)
    if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
        echo "PostgreSQL ready."; return
    fi

    # Last resort: pg_ctlcluster only if postgres is not listening at all
    if command -v pg_ctlcluster >/dev/null 2>&1; then
        echo "Attempting pg_ctlcluster start..."
        run_sudo pg_ctlcluster 18 main start 2>/dev/null || true
    fi

    wait_for "PostgreSQL" "pg_isready -h 127.0.0.1 -p 5432"
}

start_redis() {
    echo "Checking Redis..."
    if redis-cli ping >/dev/null 2>&1; then
        echo "Redis already running."; return
    fi

    # Suppress jemalloc warning
    [[ -f /proc/sys/vm/overcommit_memory ]] && \
        echo 1 > /proc/sys/vm/overcommit_memory 2>/dev/null || true

    echo "Starting Redis..."
    redis-server --daemonize yes \
        --logfile "$REDIS_LOG" \
        --pidfile "$REDIS_PID"

    wait_for "Redis" "redis-cli ping"
}

run_database_bootstrap() {
    echo "Running migrations..."
    "$PYTHON_BIN" manage.py migrate --run-syncdb

    echo "Collecting static files..."
    "$PYTHON_BIN" manage.py collectstatic --noinput --clear 2>&1 | tail -3

    [[ "$SEED_DB" != "0" ]] && {
        echo "Seeding flood data..."
        "$PYTHON_BIN" manage.py init_db --skip-confirmation
    }
}

process_alive() {
    local pid
    [[ -f "$1" ]] || return 1
    pid="$(cat "$1" 2>/dev/null || true)"
    [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

stop_process_from_pidfile() {
    process_alive "$1" || { rm -f "$1"; return; }
    local pid; pid="$(cat "$1")"
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
    rm -f "$1"
}

cleanup() {
    stop_process_from_pidfile "$LOG_DIR/celery-worker.pid"
    stop_process_from_pidfile "$LOG_DIR/celery-beat.pid"
}

start_celery_worker() {
    local pidfile="$LOG_DIR/celery-worker.pid"
    process_alive "$pidfile" && { echo "Celery worker already running."; return; }
    rm -f "$pidfile"
    echo "Starting Celery worker..."
    "$CELERY_BIN" -A floodguard worker --loglevel=warning --detach \
        --logfile="$LOG_DIR/celery-worker.log" \
        --pidfile="$pidfile"
}

start_celery_beat() {
    local pidfile="$LOG_DIR/celery-beat.pid"
    process_alive "$pidfile" && { echo "Celery beat already running."; return; }
    rm -f "$pidfile"
    echo "Starting Celery beat..."
    "$CELERY_BIN" -A floodguard beat --loglevel=warning --detach \
        --logfile="$LOG_DIR/celery-beat.log" \
        --pidfile="$pidfile"
}

start_web() {
    echo ""
    echo "========================================"
    echo " FloodGuard running"
    echo " URL:  http://127.0.0.1:$APP_PORT"
    echo " WS:   ws://127.0.0.1:$APP_PORT/ws/alerts/"
    echo " Admin: admin / admin123"
    echo "========================================"
    "$DAPHNE_BIN" -b "$APP_HOST" -p "$APP_PORT" floodguard.asgi:application
}

main() {
    cd "$ROOT_DIR"
    trap cleanup EXIT INT TERM

    echo "Starting FloodGuard..."

    need_cmd pg_isready
    need_cmd redis-cli
    need_cmd redis-server

    ensure_virtualenv
    sync_dependencies
    start_postgres
    start_redis
    run_database_bootstrap

    echo "Django system check..."
    "$PYTHON_BIN" manage.py check

    start_celery_worker
    start_celery_beat
    start_web
}

main "$@"
