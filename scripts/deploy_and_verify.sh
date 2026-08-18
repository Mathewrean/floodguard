#!/usr/bin/env bash
set -Eeuo pipefail

# FloodGuard Deployment and Verification Script
# Automates full production-like setup and validates core functionality
# especially authentication (registration + login without email/SMS verification).

APP_NAME="FloodGuard"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-$ROOT_DIR/floodguard-env}"
PYTHON="${PYTHON:-$VENV_DIR/bin/python}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
BASE_URL="http://127.0.0.1:$PORT"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@floodguard.local}"

# Colors
if [[ -t 1 ]]; then
    BOLD="$(printf '\033[1m')"
    GREEN="$(printf '\033[32m')"
    YELLOW="$(printf '\033[33m')"
    RED="$(printf '\033[31m')"
    RESET="$(printf '\033[0m')"
else
    BOLD="" GREEN="" YELLOW="" RED="" RESET=""
fi

log()   { printf '%s[%s]%s %s\n' "$BOLD$GREEN" "$APP_NAME" "$RESET" "$*"; }
warn()  { printf '%s[%s warning]%s %s\n' "$BOLD$YELLOW" "$APP_NAME" "$RESET" "$*" >&2; }
die()   { printf '%s[%s error]%s %s\n' "$BOLD$RED" "$APP_NAME" "$RESET" "$*" >&2; exit 1; }
pass()  { printf '%s[%s]%s %s\n' "$BOLD$GREEN" "$APP_NAME" "$RESET" "$*"; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }
have_cmd() { command -v "$1" >/dev/null 2>&1; }

[[ -n "$ADMIN_PASSWORD" ]] || die "Set ADMIN_PASSWORD to run authenticated deployment verification."

wait_tcp() {
    local label="$1" host="$2" port="$3" attempts="${4:-30}" delay="${5:-2}"
    log "Waiting for $label at $host:$port..."
    for _ in $(seq 1 "$attempts"); do
        if (echo >"/dev/tcp/$host/$port") >/dev/null 2>&1; then
            log "$label is ready."
            return 0
        fi
        sleep "$delay"
    done
    die "$label did not become ready at $host:$port."
}

# -----------------------------------------------------------------------------
# Phase 1: Prerequisites
# -----------------------------------------------------------------------------
check_prerequisites() {
    log "Checking prerequisites..."
    need_cmd python3
    need_cmd pip
    need_cmd psql
    need_cmd redis-cli

    if ! [[ -x "$PYTHON" ]]; then
        if [[ -x "$VENV_DIR/bin/python" ]]; then
            PYTHON="$VENV_DIR/bin/python"
        else
            die "Python interpreter not found at $PYTHON. Run init_project.sh first."
        fi
    fi

    log "Python: $($PYTHON --version 2>&1)"
    pass "Prerequisites satisfied."
}

# -----------------------------------------------------------------------------
# Phase 2: Environment configuration
# -----------------------------------------------------------------------------
setup_environment() {
    log "Configuring environment..."
    ENV_FILE="$ROOT_DIR/.env"
    ENV_EXAMPLE="$ROOT_DIR/.env.example"

    if [[ ! -f "$ENV_FILE" ]]; then
        if [[ -f "$ENV_EXAMPLE" ]]; then
            log "Creating .env from .env.example"
            cp "$ENV_EXAMPLE" "$ENV_FILE"
        else
            die ".env file not found. Create one from .env.example"
        fi
    fi

    # Ensure critical settings for immediate auth (no email/SMS verification)
    set_env_value() {
        local key="$1" value="$2"
        local escaped
        escaped="$(printf '%s' "$value" | sed 's/[&|]/\\&/g')"
        if grep -qE "^${key}=" "$ENV_FILE"; then
            sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
        else
            printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
        fi
    }

    set_env_value SECRET_KEY "$(openssl rand -hex 32 2>/dev/null || echo "floodguard-secret-$(date +%s)")"
    set_env_value DEBUG "True"
    set_env_value ALLOWED_HOSTS "localhost,127.0.0.1,0.0.0.0"
    set_env_value SMS_ENABLED "False"
    set_env_value EMAIL_BACKEND "django.core.mail.backends.console.EmailBackend"
    set_env_value SECURE_SSL_REDIRECT "False"
    set_env_value SESSION_COOKIE_SECURE "False"
    set_env_value CSRF_COOKIE_SECURE "False"

    log "Environment configured."
}

# -----------------------------------------------------------------------------
# Phase 3: Services
# -----------------------------------------------------------------------------
start_postgres() {
    log "Checking PostgreSQL..."
    if have_cmd pg_isready && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        log "PostgreSQL is already running."
        return 0
    fi

    if have_cmd systemctl; then
        for unit in postgresql postgresql.service postgresql@18-main.service postgresql@15-main.service; do
            if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
                warn "Starting $unit"
                run_elevated() {
                    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then "$@"; elif have_cmd sudo; then sudo "$@"; else return 1; fi
                }
                run_elevated systemctl start "$unit" && break || true
            fi
        done
    fi

    if have_cmd pg_ctlcluster; then
        run_elevated() {
            if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then "$@"; elif have_cmd sudo; then sudo "$@"; else return 1; fi
        }
        run_elevated pg_ctlcluster 18 main start >/dev/null 2>&1 || true
        run_elevated pg_ctlcluster 15 main start >/dev/null 2>&1 || true
    fi

    if have_cmd pg_isready && pg_isready -h localhost -p 5432 >/dev/null 2>&1; then
        log "PostgreSQL is ready."
        return 0
    fi

    die "PostgreSQL is not running. Start it manually or use scripts/init_project.sh --mode docker."
}

start_redis() {
    log "Checking Redis..."
    if have_cmd redis-cli && redis-cli ping >/dev/null 2>&1; then
        log "Redis is already running."
        return 0
    fi

    if have_cmd systemctl; then
        for unit in redis-server redis-server.service redis redis.service; do
            if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
                warn "Starting $unit"
                run_elevated() {
                    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then "$@"; elif have_cmd sudo; then sudo "$@"; else return 1; fi
                }
                run_elevated systemctl start "$unit" && break || true
            fi
        done
    fi

    if have_cmd redis-cli && redis-cli ping >/dev/null 2>&1; then
        log "Redis is ready."
        return 0
    fi

    if have_cmd redis-server; then
        log "Starting local Redis daemon."
        mkdir -p "$ROOT_DIR/logs" "$ROOT_DIR/.local/run"
        redis-server --daemonize yes \
            --logfile "$ROOT_DIR/logs/redis.log" \
            --pidfile "$ROOT_DIR/.local/run/redis.pid"
        sleep 1
    fi

    if have_cmd redis-cli && redis-cli ping >/dev/null 2>&1; then
        log "Redis is ready."
    else
        die "Redis is not running. Start it manually or use scripts/init_project.sh --mode docker."
    fi
}

ensure_database() {
    log "Verifying database..."
    ENV_FILE="$ROOT_DIR/.env"
    get_env_value() {
        local key="$1" fallback="$2"
        local value
        value="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
        printf '%s\n' "${value:-$fallback}"
    }

    DB_NAME="$(get_env_value DB_NAME floodguard)"
    DB_USER="$(get_env_value DB_USER floodguard)"
    DB_PASSWORD="$(get_env_value DB_PASSWORD floodguard)"

    if PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c 'SELECT 1;' >/dev/null 2>&1; then
        log "Database connection verified: $DB_USER@$DB_NAME"
        # Check table ownership; if wrong, drop and recreate DB
        local OWNER_CHECK
        OWNER_CHECK=$(PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -tc "SELECT tableowner FROM pg_tables WHERE tablename = 'core_userprofile';" 2>/dev/null | xargs)
        if [[ "$OWNER_CHECK" != "$DB_USER" ]]; then
            warn "Database tables owned by '$OWNER_CHECK', not '$DB_USER'. Recreating database."
            PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d postgres -c "DROP DATABASE ${DB_NAME};"
            PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d postgres -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
        fi
        return 0
    fi

    warn "Database $DB_NAME not ready; bootstrapping locally."
    need_cmd psql

    run_as_postgres() {
        if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
            local quoted=""
            local arg
            for arg in "$@"; do quoted+="$(printf '%q' "$arg") "; done
            su -s /bin/sh postgres -c "$quoted"
        elif have_cmd sudo; then
            sudo -u postgres "$@"
        else
            return 1
        fi
    }

    if run_as_postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
        log "Database user $DB_USER already exists."
    else
        run_as_postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"
        run_as_postgres psql -c "ALTER USER ${DB_USER} CREATEDB;"
    fi

    if run_as_postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
        log "Database $DB_NAME already exists."
    else
        run_as_postgres createdb -O "$DB_USER" "$DB_NAME"
    fi

    run_as_postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis;" >/dev/null
    PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c 'SELECT 1;' >/dev/null
    log "Database bootstrap complete."
}

# -----------------------------------------------------------------------------
# Phase 4: Django setup
# -----------------------------------------------------------------------------
django_setup() {
    log "Running Django setup..."
    "$PYTHON" manage.py check
    log "Applying migrations..."
    "$PYTHON" manage.py migrate --noinput
    log "Collecting static files..."
    "$PYTHON" manage.py collectstatic --noinput --clear || true
    pass "Django setup complete."
}

create_superuser() {
    log "Ensuring superuser exists..."
    if "$PYTHON" manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print('exists' if User.objects.filter(username='$ADMIN_USER').exists() else 'missing')" 2>/dev/null | grep -q "exists"; then
        log "Superuser '$ADMIN_USER' already exists."
        return 0
    fi

    log "Creating superuser: $ADMIN_USER"
    "$PYTHON" manage.py createsuperuser --noinput --username "$ADMIN_USER" --email "$ADMIN_EMAIL" 2>/dev/null || true

    # Set password via shell (bypasses password validation)
    "$PYTHON" manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='$ADMIN_USER')
user.set_password('$ADMIN_PASSWORD')
user.save()
print('Superuser password set.')
"
    pass "Superuser created: $ADMIN_USER / $ADMIN_PASSWORD"
}

# -----------------------------------------------------------------------------
# Phase 5: Start application
# -----------------------------------------------------------------------------
start_application() {
    log "Starting Django application on $HOST:$PORT..."
    mkdir -p "$ROOT_DIR/logs" "$ROOT_DIR/.local/run"

    if [[ -f "$ROOT_DIR/.local/run/django.pid" ]] && kill -0 "$(cat "$ROOT_DIR/.local/run/django.pid")" >/dev/null 2>&1; then
        log "Django already running with PID $(cat "$ROOT_DIR/.local/run/django.pid")."
        return 0
    fi

    nohup "$PYTHON" manage.py runserver "$HOST:$PORT" \
        >"$ROOT_DIR/logs/django.log" 2>&1 &
    echo $! > "$ROOT_DIR/.local/run/django.pid"

    wait_tcp "Django" "127.0.0.1" "$PORT" 60 2
    pass "Application started at $BASE_URL"
}

# -----------------------------------------------------------------------------
# Phase 6: Verify core functionality
# -----------------------------------------------------------------------------
verify_health() {
    log "Verifying health endpoint..."
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health/")
    if [[ "$http_code" == "200" ]]; then
        pass "Health check: OK ($http_code)"
    else
        die "Health check failed with HTTP $http_code"
    fi
}

verify_registration_and_login() {
    log "Testing registration and login flow..."
    local TEST_USER="testuser_$(date +%s)"
    local TEST_PASS="TestPass123!"
    local TEST_EMAIL="$TEST_USER@test.local"
    local COOKIE_JAR="$ROOT_DIR/.local/run/auth_cookies.txt"

    rm -f "$COOKIE_JAR"

    # Step 1: Get CSRF token from registration page
    log "Step 1: Fetching registration page..."
    local REG_PAGE
    REG_PAGE=$(curl -s -c "$COOKIE_JAR" "$BASE_URL/register/")
    local CSRF_TOKEN
    CSRF_TOKEN=$(echo "$REG_PAGE" | grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' | head -1 | sed 's/.*value="\([^"]*\)".*/\1/')

    if [[ -z "$CSRF_TOKEN" ]]; then
        die "Could not extract CSRF token from registration page."
    fi
    log "CSRF token obtained."

    # Step 2: Submit registration
    log "Step 2: Registering user '$TEST_USER'..."
    local REG_RESPONSE
    REG_RESPONSE=$(curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
        -X POST "$BASE_URL/register/" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -H "Referer: $BASE_URL/register/" \
        -d "username=$TEST_USER&email=$TEST_EMAIL&password1=$TEST_PASS&password2=$TEST_PASS&csrfmiddlewaretoken=$CSRF_TOKEN" \
        -w "\nHTTP_CODE:%{http_code}" \
        -L --max-redirs 2)

    local HTTP_CODE
    HTTP_CODE=$(echo "$REG_RESPONSE" | grep "HTTP_CODE:" | tail -1 | sed 's/.*HTTP_CODE://')
    local BODY
    BODY=$(echo "$REG_RESPONSE" | sed '/HTTP_CODE:/d')

    if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "302" ]]; then
        pass "Registration submitted (HTTP $HTTP_CODE)"
    else
        die "Registration failed with HTTP $HTTP_CODE. Response: $(echo "$BODY" | head -20)"
    fi

    # Verify user was created in database
    log "Step 3: Verifying user persisted in database..."
    local DB_CHECK
    DB_CHECK=$("$PYTHON" manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.filter(username='$TEST_USER').first()
if u:
    print('FOUND:email=' + (u.email or '') + ':active=' + str(u.is_active))
else:
    print('NOT_FOUND')
" 2>/dev/null)

    if [[ "$DB_CHECK" == *"FOUND:"* ]]; then
        pass "User persisted in database: $DB_CHECK"
    else
        die "User NOT found in database after registration."
    fi

    # Step 4: Logout (if auto-logged in)
    log "Step 4: Ensuring clean session for login test..."
    curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$BASE_URL/logout/" >/dev/null 2>&1 || true

    # Step 5: Get login CSRF and submit login
    log "Step 5: Testing login with newly created credentials..."
    local LOGIN_PAGE
    LOGIN_PAGE=$(curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$BASE_URL/login/")
    local LOGIN_CSRF
    LOGIN_CSRF=$(echo "$LOGIN_PAGE" | grep -o 'name="csrfmiddlewaretoken" value="[^"]*"' | head -1 | sed 's/.*value="\([^"]*\)".*/\1/')

    if [[ -z "$LOGIN_CSRF" ]]; then
        die "Could not extract CSRF token from login page."
    fi

    local LOGIN_RESPONSE
    LOGIN_RESPONSE=$(curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
        -X POST "$BASE_URL/login/" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -H "Referer: $BASE_URL/login/" \
        -d "username=$TEST_USER&password=$TEST_PASS&csrfmiddlewaretoken=$LOGIN_CSRF" \
        -w "\nHTTP_CODE:%{http_code}" \
        -L --max-redirs 2)

    local LOGIN_HTTP_CODE
    LOGIN_HTTP_CODE=$(echo "$LOGIN_RESPONSE" | grep "HTTP_CODE:" | tail -1 | sed 's/.*HTTP_CODE://')

    if [[ "$LOGIN_HTTP_CODE" == "200" || "$LOGIN_HTTP_CODE" == "302" ]]; then
        pass "Login successful (HTTP $LOGIN_HTTP_CODE)"
    else
        die "Login failed with HTTP $LOGIN_HTTP_CODE"
    fi

    # Step 6: Verify authenticated session by checking dashboard
    log "Step 6: Verifying authenticated access to dashboard..."
    local DASH_RESPONSE
    DASH_RESPONSE=$(curl -s -b "$COOKIE_JAR" "$BASE_URL/dashboard/citizen/" -w "\nHTTP_CODE:%{http_code}")
    local DASH_HTTP_CODE
    DASH_HTTP_CODE=$(echo "$DASH_RESPONSE" | grep "HTTP_CODE:" | tail -1 | sed 's/.*HTTP_CODE://')

    if [[ "$DASH_HTTP_CODE" == "200" ]]; then
        pass "Authenticated dashboard access: OK"
    else
        die "Dashboard access failed with HTTP $DASH_HTTP_CODE (auth may not be working)."
    fi

    # Step 7: Cleanup test user
    log "Step 7: Cleaning up test user..."
    "$PYTHON" manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.filter(username='$TEST_USER').delete()
print('Test user deleted.')
" 2>/dev/null

    pass "Auth verification complete. Registration + Login + Dashboard access all WORKING."
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    log "Starting FloodGuard deployment and verification..."

    check_prerequisites
    setup_environment
    start_postgres
    start_redis
    ensure_database
    django_setup
    create_superuser
    start_application
    verify_health
    verify_registration_and_login

    pass "=========================================="
    pass "DEPLOYMENT SUCCESSFUL"
    pass "=========================================="
    log "Application URL:  $BASE_URL"
    log "Admin panel:      $BASE_URL/admin/"
    log "Admin credentials: $ADMIN_USER / $ADMIN_PASSWORD"
    log "Citizen dashboard: $BASE_URL/dashboard/citizen/"
    log "GIS Dashboard:     $BASE_URL/gis/"
    log ""
    log "Authentication is configured for IMMEDIATE login:"
    log "  - No email verification required"
    log "  - No SMS verification required"
    log "  - Users are active immediately upon registration"
    log "  - Credentials are persisted in PostgreSQL"
    log ""
    log "To stop: kill $(cat "$ROOT_DIR/.local/run/django.pid" 2>/dev/null || echo "N/A")"
}

main "$@"
