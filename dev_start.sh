#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/floodguard_env"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
CELERY_BIN="$VENV_DIR/bin/celery"
DAPHNE_BIN="$VENV_DIR/bin/daphne"
LOG_DIR="$ROOT_DIR/logs"
DEPS_MARKER="$VENV_DIR/.deps_synced"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
POSTGRES_CLUSTER="${POSTGRES_CLUSTER:-18 main}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgresql@18-main.service}"
REDIS_LOG="${REDIS_LOG:-/tmp/redis-floodguard.log}"
REDIS_PID="${REDIS_PID:-/tmp/redis-floodguard.pid}"
SYNC_DEPS="${SYNC_DEPS:-auto}"
SEED_DB="${SEED_DB:-1}"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-floodguard.settings}"
export PYTHONUNBUFFERED=1

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
    local attempts="${3:-30}"
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

ensure_virtualenv() {
    if [[ ! -x "$PYTHON_BIN" ]]; then
        need_cmd python3
        echo "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi

    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
}

sync_dependencies() {
    mkdir -p "$LOG_DIR"

    if [[ "$SYNC_DEPS" == "0" ]]; then
        echo "Skipping dependency sync."
        return
    fi

    if [[ "$SYNC_DEPS" == "1" || ! -f "$DEPS_MARKER" || "$ROOT_DIR/requirements.txt" -nt "$DEPS_MARKER" ]]; then
        echo "Synchronising Python dependencies..."
        "$PYTHON_BIN" -m pip install --upgrade pip
        "$PYTHON_BIN" -m pip install -r "$ROOT_DIR/requirements.txt"
        touch "$DEPS_MARKER"
    else
        echo "Python dependencies are already up to date."
    fi
}

start_postgres() {
    echo "Checking PostgreSQL..."
    if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
        echo "PostgreSQL is already accepting connections."
        return
    fi

    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet "$POSTGRES_SERVICE"; then
            echo "$POSTGRES_SERVICE is active."
        else
            echo "Starting $POSTGRES_SERVICE..."
            run_sudo systemctl start "$POSTGRES_SERVICE" || true
        fi
    fi

    if ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 && command -v pg_ctlcluster >/dev/null 2>&1; then
        echo "Starting PostgreSQL cluster: $POSTGRES_CLUSTER..."
        run_sudo pg_ctlcluster $POSTGRES_CLUSTER start || true
    fi

    wait_for "PostgreSQL" "pg_isready -h 127.0.0.1 -p 5432"
}

start_redis() {
    echo "Checking Redis..."
    if redis-cli ping >/dev/null 2>&1; then
        echo "Redis is already running."
        return
    fi

    if [[ -f /proc/sys/vm/overcommit_memory ]]; then
        current_overcommit="$(cat /proc/sys/vm/overcommit_memory || echo 0)"
        if [[ "$current_overcommit" -ne 1 ]]; then
            echo "Setting vm.overcommit_memory = 1 (required by Redis)"
            echo 1 > /proc/sys/vm/overcommit_memory || true
        fi
    fi

    echo "Starting Redis..."
    redis-server --daemonize yes \
        --logfile "$REDIS_LOG" \
        --pidfile "$REDIS_PID"

    wait_for "Redis" "redis-cli ping"
}

run_database_bootstrap() {
    echo "Applying database migrations..."
    "$PYTHON_BIN" manage.py migrate --run-syncdb

    echo "Collecting static files..."
    "$PYTHON_BIN" manage.py collectstatic --noinput --clear

    if [[ "$SEED_DB" != "0" ]]; then
        echo "Initialising database with real flood data..."
        "$PYTHON_BIN" manage.py init_db --skip-confirmation
    fi
}

process_alive() {
    local pidfile="$1"
    [[ -f "$pidfile" ]] || return 1
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

stop_process_from_pidfile() {
    local pidfile="$1"
    if process_alive "$pidfile"; then
        local pid
        pid="$(cat "$pidfile")"
        kill "$pid" >/dev/null 2>&1 || true
        wait "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
}

cleanup() {
    stop_process_from_pidfile "$LOG_DIR/celery-worker.pid"
    stop_process_from_pidfile "$LOG_DIR/celery-beat.pid"
}

start_celery_worker() {
    local pidfile="$LOG_DIR/celery-worker.pid"
    if process_alive "$pidfile"; then
        echo "Celery worker is already running."
        return
    fi

    rm -f "$pidfile"
    echo "Starting Celery worker..."
    "$CELERY_BIN" -A floodguard worker --loglevel=info --detach \
        --logfile="$LOG_DIR/celery-worker.log" \
        --pidfile="$pidfile"
}

start_celery_beat() {
    local pidfile="$LOG_DIR/celery-beat.pid"
    if process_alive "$pidfile"; then
        echo "Celery beat is already running."
        return
    fi

    rm -f "$pidfile"
    echo "Starting Celery beat..."
    "$CELERY_BIN" -A floodguard beat --loglevel=info --detach \
        --logfile="$LOG_DIR/celery-beat.log" \
        --pidfile="$pidfile"
}

start_web() {
    echo "Starting ASGI server on http://$APP_HOST:$APP_PORT"
    echo "Admin: http://127.0.0.1:$APP_PORT/admin/"
    echo "Credentials: admin / admin123"
    "$DAPHNE_BIN" -b "$APP_HOST" -p "$APP_PORT" floodguard.asgi:application
}

main() {
    cd "$ROOT_DIR"
    trap cleanup EXIT INT TERM

    echo "Starting FloodGuard development environment..."

    need_cmd pg_isready
    need_cmd redis-cli
    need_cmd redis-server

    ensure_virtualenv
    sync_dependencies

    start_postgres
    start_redis
    run_database_bootstrap

    echo "Checking Django project..."
    "$PYTHON_BIN" manage.py check

    start_celery_worker
    start_celery_beat

    echo ""
    echo "========================================"
    echo "FloodGuard is ready."
    echo "Local URL: http://127.0.0.1:$APP_PORT"
    echo "WebSocket: ws://127.0.0.1:$APP_PORT/ws/alerts/"
    echo "========================================"

    start_web
}

main "$@"
