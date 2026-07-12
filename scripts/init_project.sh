#!/usr/bin/env bash
set -Eeuo pipefail

# FloodGuard one-command project initializer.
# Default behavior:
#   - Use Docker Compose when Docker and Compose are available.
#   - Fall back to a local Python virtualenv plus PostgreSQL/Redis services.
#   - Create a local .env from .env.example when needed.
#   - Install dependencies, run migrations, collect static assets, and start services.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="FloodGuard"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
ENV_EXAMPLE="${ENV_EXAMPLE:-$ROOT_DIR/.env.example}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/floodguard-env}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
MODE="${MODE:-auto}"
DETACH="${DETACH:-0}"
INSTALL_DEPS="${INSTALL_DEPS:-1}"
START_SERVICES="${START_SERVICES:-1}"
RUN_TESTS="${RUN_TESTS:-0}"
SKIP_COLLECTSTATIC="${SKIP_COLLECTSTATIC:-0}"
CHECK_ONLY="${CHECK_ONLY:-0}"
LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/.local/run"
DEPS_MARKER="$VENV_DIR/.requirements.synced"

if [[ -t 1 ]]; then
    BOLD="$(printf '\033[1m')"
    GREEN="$(printf '\033[32m')"
    YELLOW="$(printf '\033[33m')"
    RED="$(printf '\033[31m')"
    RESET="$(printf '\033[0m')"
else
    BOLD="" GREEN="" YELLOW="" RED="" RESET=""
fi

log() { printf '%s[%s]%s %s\n' "$BOLD$GREEN" "$APP_NAME" "$RESET" "$*"; }
warn() { printf '%s[%s warning]%s %s\n' "$BOLD$YELLOW" "$APP_NAME" "$RESET" "$*" >&2; }
die() { printf '%s[%s error]%s %s\n' "$BOLD$RED" "$APP_NAME" "$RESET" "$*" >&2; exit 1; }

on_error() {
    local exit_code=$?
    die "Setup failed at line ${BASH_LINENO[0]} with exit code $exit_code."
}
trap on_error ERR

usage() {
    cat <<USAGE
Usage: scripts/init_project.sh [options]

Options:
  --mode auto|docker|local   Startup mode. Default: auto.
  --detach                  Run local Django/Celery processes in the background.
  --foreground              Run local Django server in the foreground. Default for local mode.
  --no-install              Skip Python dependency installation.
  --no-services             Skip starting PostgreSQL/Redis/Docker Compose services.
  --run-tests               Run the test suite after setup.
  --skip-collectstatic      Skip collectstatic.
  --check-only              Validate dependencies/configuration and exit.
  --host HOST               Django bind host for local mode. Default: 0.0.0.0.
  --port PORT               Django bind port for local mode. Default: 8000.
  -h, --help                Show this help text.

Examples:
  scripts/init_project.sh
  scripts/init_project.sh --mode docker
  scripts/init_project.sh --mode local --detach
  scripts/init_project.sh --mode local --run-tests
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            MODE="${2:-}"
            shift 2
            ;;
        --detach)
            DETACH=1
            shift
            ;;
        --foreground)
            DETACH=0
            shift
            ;;
        --no-install)
            INSTALL_DEPS=0
            shift
            ;;
        --no-services)
            START_SERVICES=0
            shift
            ;;
        --run-tests)
            RUN_TESTS=1
            shift
            ;;
        --skip-collectstatic)
            SKIP_COLLECTSTATIC=1
            shift
            ;;
        --check-only)
            CHECK_ONLY=1
            shift
            ;;
        --host)
            HOST="${2:-}"
            shift 2
            ;;
        --port)
            PORT="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

[[ "$MODE" =~ ^(auto|docker|local)$ ]] || die "--mode must be auto, docker, or local."
[[ -n "$HOST" ]] || die "--host cannot be empty."
[[ -n "$PORT" ]] || die "--port cannot be empty."

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

have_cmd() {
    command -v "$1" >/dev/null 2>&1
}

run_elevated() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        "$@"
    elif have_cmd sudo; then
        sudo "$@"
    else
        return 1
    fi
}

run_as_postgres() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        local quoted=""
        local arg
        for arg in "$@"; do
            quoted+="$(printf '%q' "$arg") "
        done
        su -s /bin/sh postgres -c "$quoted"
    elif have_cmd sudo; then
        sudo -u postgres "$@"
    else
        return 1
    fi
}

secret_key() {
    if have_cmd openssl; then
        openssl rand -hex 32
    elif [[ -r /proc/sys/kernel/random/uuid ]]; then
        printf 'floodguard-%s-%s\n' "$(cat /proc/sys/kernel/random/uuid)" "$(date +%s)"
    else
        printf 'floodguard-%s-%s\n' "$RANDOM" "$(date +%s)"
    fi
}

set_env_value() {
    local key="$1"
    local value="$2"
    local escaped
    escaped="$(printf '%s' "$value" | sed 's/[&|]/\\&/g')"

    if grep -qE "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

get_env_value() {
    local key="$1"
    local fallback="$2"
    local value
    value="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
    printf '%s\n' "${value:-$fallback}"
}

ensure_env_file() {
    local db_host="$1"
    local redis_url="$2"

    if [[ ! -f "$ENV_FILE" ]]; then
        log "Creating .env from .env.example."
        [[ -f "$ENV_EXAMPLE" ]] || die ".env is missing and .env.example was not found."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    else
        log ".env already exists; preserving existing values where possible."
    fi

    local existing_secret
    existing_secret="$(get_env_value SECRET_KEY "")"
    if [[ -z "$existing_secret" || "$existing_secret" == "your-secret-key-here-change-in-production" ]]; then
        set_env_value SECRET_KEY "$(secret_key)"
    fi

    set_env_value DEBUG "${DEBUG:-True}"
    set_env_value ALLOWED_HOSTS "${ALLOWED_HOSTS:-localhost,127.0.0.1,0.0.0.0}"
    set_env_value DB_NAME "${DB_NAME:-floodguard}"
    set_env_value DB_USER "${DB_USER:-floodguard}"
    set_env_value DB_PASSWORD "${DB_PASSWORD:-floodguard}"
    set_env_value DB_HOST "${DB_HOST:-$db_host}"
    set_env_value DB_PORT "${DB_PORT:-5432}"
    set_env_value DATABASE_URL ""
    set_env_value REDIS_URL "$redis_url"
    set_env_value REDIS_HOST "${REDIS_HOST:-localhost}"
    set_env_value REDIS_PORT "${REDIS_PORT:-6379}"
    set_env_value DB_SSL_REQUIRE "${DB_SSL_REQUIRE:-False}"
    set_env_value SECURE_SSL_REDIRECT "${SECURE_SSL_REDIRECT:-False}"

    log "Environment file ready: $ENV_FILE"
}

compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        printf 'docker compose'
    elif have_cmd docker-compose; then
        printf 'docker-compose'
    else
        return 1
    fi
}

docker_available() {
    have_cmd docker && docker info >/dev/null 2>&1 && compose_cmd >/dev/null 2>&1
}

wait_tcp() {
    local label="$1"
    local host="$2"
    local port="$3"
    local attempts="${4:-30}"
    local delay="${5:-2}"

    log "Waiting for $label at $host:$port."
    for _ in $(seq 1 "$attempts"); do
        if (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1; then
            log "$label is ready."
            return 0
        fi
        sleep "$delay"
    done
    die "$label did not become ready at $host:$port."
}

choose_python() {
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        printf '%s\n' "$VENV_DIR/bin/python"
        return
    fi
    if have_cmd "python$PYTHON_VERSION"; then
        printf '%s\n' "python$PYTHON_VERSION"
        return
    fi
    if have_cmd uv; then
        printf '%s\n' "uv"
        return
    fi
    if have_cmd python3; then
        warn "python$PYTHON_VERSION not found; falling back to python3."
        printf '%s\n' "python3"
        return
    fi
    die "No suitable Python found. Install Python $PYTHON_VERSION or uv."
}

ensure_virtualenv() {
    mkdir -p "$LOG_DIR" "$RUN_DIR"
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        log "Using existing virtualenv: $VENV_DIR"
        return
    fi

    local py
    py="$(choose_python)"
    if [[ "$py" == "uv" ]]; then
        log "Creating virtualenv with uv and Python $PYTHON_VERSION."
        uv venv --python "$PYTHON_VERSION" --seed "$VENV_DIR"
    else
        log "Creating virtualenv with $py."
        "$py" -m venv "$VENV_DIR"
        "$VENV_DIR/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
}

install_dependencies() {
    [[ "$INSTALL_DEPS" == "1" ]] || { log "Skipping dependency installation."; return; }
    ensure_virtualenv
    if [[ ! -f "$DEPS_MARKER" || requirements.txt -nt "$DEPS_MARKER" ]]; then
        log "Installing Python dependencies."
        "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
        "$VENV_DIR/bin/python" -m pip install -r requirements.txt
        touch "$DEPS_MARKER"
    else
        log "Python dependencies are already up to date."
    fi
}

start_postgres_local() {
    if [[ "$START_SERVICES" != "1" ]]; then
        log "Skipping PostgreSQL startup."
        return
    fi

    if have_cmd pg_isready && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        log "PostgreSQL is already running."
        return
    fi

    if have_cmd systemctl; then
        for unit in postgresql postgresql.service postgresql@18-main.service postgresql@15-main.service; do
            if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
                warn "Attempting to start $unit."
                run_elevated systemctl start "$unit" || true
                break
            fi
        done
    fi

    if have_cmd pg_ctlcluster; then
        run_elevated pg_ctlcluster 18 main start >/dev/null 2>&1 || true
        run_elevated pg_ctlcluster 15 main start >/dev/null 2>&1 || true
    fi

    if have_cmd pg_isready && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        log "PostgreSQL is ready."
    else
        die "PostgreSQL is not running. Start it manually or use --mode docker."
    fi
}

start_redis_local() {
    if [[ "$START_SERVICES" != "1" ]]; then
        log "Skipping Redis startup."
        return
    fi

    if have_cmd redis-cli && redis-cli ping >/dev/null 2>&1; then
        log "Redis is already running."
        return
    fi

    if have_cmd systemctl; then
        for unit in redis-server redis-server.service redis redis.service; do
            if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
                warn "Attempting to start $unit."
                run_elevated systemctl start "$unit" || true
                break
            fi
        done
    fi

    if have_cmd redis-cli && redis-cli ping >/dev/null 2>&1; then
        log "Redis is ready."
        return
    fi

    if have_cmd redis-server; then
        log "Starting project-local Redis daemon."
        redis-server --daemonize yes \
            --logfile "$LOG_DIR/redis.log" \
            --pidfile "$RUN_DIR/redis.pid"
        sleep 1
    fi

    if have_cmd redis-cli && redis-cli ping >/dev/null 2>&1; then
        log "Redis is ready."
    else
        die "Redis is not running. Start it manually or use --mode docker."
    fi
}

ensure_database_local() {
    local db_name db_user db_password
    db_name="$(get_env_value DB_NAME floodguard)"
    db_user="$(get_env_value DB_USER floodguard)"
    db_password="$(get_env_value DB_PASSWORD floodguard)"

    if PGPASSWORD="$db_password" psql -h localhost -U "$db_user" -d "$db_name" -c 'SELECT 1;' >/dev/null 2>&1; then
        log "Database connection verified for $db_user@$db_name."
        return
    fi

    warn "Database $db_name or user $db_user is not ready; attempting local bootstrap."
    if ! have_cmd psql; then
        die "psql is required for local database bootstrap."
    fi

    if run_as_postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${db_user}'" | grep -q 1; then
        log "Database user $db_user already exists."
    else
        run_as_postgres psql -c "CREATE USER ${db_user} WITH PASSWORD '${db_password}';"
        run_as_postgres psql -c "ALTER USER ${db_user} CREATEDB;"
    fi

    if run_as_postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${db_name}'" | grep -q 1; then
        log "Database $db_name already exists."
    else
        run_as_postgres createdb -O "$db_user" "$db_name"
    fi

    run_as_postgres psql -d "$db_name" -c "CREATE EXTENSION IF NOT EXISTS postgis;" >/dev/null
    PGPASSWORD="$db_password" psql -h localhost -U "$db_user" -d "$db_name" -c 'SELECT 1;' >/dev/null
    log "Database bootstrap complete."
}

django_manage() {
    "$VENV_DIR/bin/python" manage.py "$@"
}

run_django_setup() {
    log "Running Django system check."
    django_manage check

    log "Applying database migrations."
    django_manage migrate --noinput

    if [[ "$SKIP_COLLECTSTATIC" == "1" ]]; then
        log "Skipping collectstatic."
    else
        log "Collecting static files."
        django_manage collectstatic --noinput --clear
    fi

    if [[ "$RUN_TESTS" == "1" ]]; then
        log "Running test suite."
        "$VENV_DIR/bin/python" -m pytest tests/ -q --tb=short
    fi
}

start_background_process() {
    local name="$1"
    shift
    local pid_file="$RUN_DIR/${name}.pid"
    local log_file="$LOG_DIR/${name}.log"

    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1; then
        log "$name already running with PID $(cat "$pid_file")."
        return
    fi

    log "Starting $name in background. Log: $log_file"
    nohup "$@" >"$log_file" 2>&1 &
    printf '%s\n' "$!" >"$pid_file"
}

start_local_app() {
    mkdir -p "$LOG_DIR" "$RUN_DIR"
    start_background_process celery-worker "$VENV_DIR/bin/celery" -A floodguard worker -l info
    start_background_process celery-beat "$VENV_DIR/bin/celery" -A floodguard beat -l info

    if [[ "$DETACH" == "1" ]]; then
        start_background_process django-web "$VENV_DIR/bin/python" manage.py runserver "$HOST:$PORT"
        log "Local stack started in background."
        log "Open: http://127.0.0.1:$PORT/"
        log "Logs: $LOG_DIR"
    else
        log "Starting Django development server in foreground."
        log "Open: http://127.0.0.1:$PORT/"
        "$VENV_DIR/bin/python" manage.py runserver "$HOST:$PORT"
    fi
}

run_docker_mode() {
    need_cmd docker
    docker info >/dev/null 2>&1 || die "Docker daemon is not running."
    local compose
    compose="$(compose_cmd)" || die "Docker Compose is not installed."

    ensure_env_file "db" "redis://redis:6379/0"

    log "Starting Docker database and Redis services."
    $compose up -d db redis
    wait_tcp PostgreSQL localhost 5432 45 2
    wait_tcp Redis localhost 6379 45 2

    log "Building application containers."
    $compose build web celery celery-beat

    log "Running migrations inside the web container."
    $compose run --rm web python manage.py migrate --noinput

    if [[ "$SKIP_COLLECTSTATIC" == "1" ]]; then
        log "Skipping collectstatic."
    else
        log "Collecting static files inside the web container."
        $compose run --rm web python manage.py collectstatic --noinput --clear
    fi

    if [[ "$RUN_TESTS" == "1" ]]; then
        log "Running tests inside the web container."
        $compose run --rm web python -m pytest tests/ -q --tb=short
    fi

    log "Starting full Docker stack."
    $compose up -d web celery celery-beat
    log "Docker stack started."
    log "Open: http://127.0.0.1:8000/"
    log "Tail logs with: $compose logs -f"
}

run_local_mode() {
    ensure_env_file "localhost" "redis://localhost:6379/0"
    install_dependencies
    start_postgres_local
    start_redis_local
    ensure_database_local
    run_django_setup
    start_local_app
}

run_check_only() {
    log "Running setup preflight checks only."

    have_cmd bash || die "bash is required."
    have_cmd sed || die "sed is required."
    have_cmd grep || die "grep is required."

    if [[ -f "$ENV_FILE" ]]; then
        log ".env exists."
    elif [[ -f "$ENV_EXAMPLE" ]]; then
        warn ".env is missing; startup will create it from .env.example."
    else
        die "Neither .env nor .env.example exists."
    fi

    if docker_available; then
        log "Docker and Docker Compose are available."
    else
        warn "Docker Compose is unavailable; startup will use local mode."
    fi

    if [[ -x "$VENV_DIR/bin/python" ]]; then
        log "Virtualenv exists: $VENV_DIR"
        "$VENV_DIR/bin/python" --version
    elif have_cmd "python$PYTHON_VERSION"; then
        log "Python $PYTHON_VERSION is available for virtualenv creation."
    elif have_cmd uv; then
        log "uv is available and can provision Python $PYTHON_VERSION."
    else
        warn "No Python $PYTHON_VERSION or uv found; local mode may fail."
    fi

    if have_cmd pg_isready && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        log "PostgreSQL is reachable on localhost:5432."
    else
        warn "PostgreSQL is not currently reachable on localhost:5432."
    fi

    if have_cmd redis-cli && redis-cli ping >/dev/null 2>&1; then
        log "Redis is responding to ping."
    else
        warn "Redis is not currently responding."
    fi

    log "Preflight checks completed."
}

main() {
    log "Initializing project in $ROOT_DIR"

    if [[ "$CHECK_ONLY" == "1" ]]; then
        run_check_only
        return
    fi

    if [[ "$MODE" == "docker" ]]; then
        run_docker_mode
    elif [[ "$MODE" == "local" ]]; then
        run_local_mode
    elif docker_available; then
        log "Auto mode selected Docker Compose."
        run_docker_mode
    else
        warn "Docker Compose is not available; falling back to local mode."
        run_local_mode
    fi
}

main "$@"
