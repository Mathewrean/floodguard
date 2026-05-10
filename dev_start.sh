#!/bin/bash
set -e
echo "Starting FloodGuard development environment..."

# PostgreSQL - use systemctl status check.
if systemctl is-active --quiet postgresql@18-main.service; then
    echo "PostgreSQL 18 is already running."
else
    echo "Starting PostgreSQL 18..."
    sudo systemctl start postgresql@18-main.service
fi

# Redis - use direct daemon, not systemctl, to avoid port conflicts.
if redis-cli ping > /dev/null 2>&1; then
    echo "Redis is already running."
else
    echo "Starting Redis..."
    redis-server --daemonize yes \
        --logfile /tmp/redis-floodguard.log \
        --pidfile /tmp/redis-floodguard.pid
    sleep 1
    redis-cli ping > /dev/null 2>&1 && echo "Redis started." \
        || echo "WARNING: Redis may have failed. Check /tmp/redis-floodguard.log"
fi

echo "Applying database migrations..."
python manage.py migrate --run-syncdb

echo "Initialising database with real flood data..."
python manage.py init_db --skip-confirmation

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear 2>&1 | tail -3

echo "Starting Celery worker..."
mkdir -p logs
pkill -f "celery -A floodguard worker" 2>/dev/null || true
sleep 1
celery -A floodguard worker --loglevel=warning --detach \
    --logfile=logs/celery.log --pidfile=logs/celery.pid
echo "Celery worker started."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "FloodGuard running at http://0.0.0.0:8000"
echo "Admin: http://127.0.0.1:8000/admin/"
echo "Credentials: admin / admin123"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
daphne -b 0.0.0.0 -p 8000 floodguard.asgi:application
