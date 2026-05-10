#!/bin/bash
set -e
echo "Starting FloodGuard development environment..."

# Start PostgreSQL if not running
if ! systemctl is-active --quiet postgresql@18-main.service; then
    echo "Starting PostgreSQL 18..."
    sudo systemctl start postgresql@18-main.service
else
    echo "PostgreSQL 18 is already running."
fi

# Start Redis if not running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis..."
    redis-server --daemonize yes
else
    echo "Redis is already running."
fi

# Apply any pending migrations
echo "Applying database migrations..."
python manage.py migrate --run-syncdb

# Initialise database with real data
echo "Initialising database with real flood data..."
python manage.py init_db --skip-confirmation

# Start Celery worker in background
echo "Starting Celery worker..."
celery -A floodguard worker --loglevel=warning --detach \
    --logfile=logs/celery.log --pidfile=logs/celery.pid

# Start development server
echo "Starting development server on http://0.0.0.0:8000"
daphne -b 0.0.0.0 -p 8000 floodguard.asgi:application
