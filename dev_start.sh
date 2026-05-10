#!/bin/bash
set -e
echo "Starting FloodGuard development environment..."

# Start PostgreSQL if not running
if ! pg_ctlcluster 15 main status > /dev/null 2>&1; then
    echo "Starting PostgreSQL 15..."
    sudo pg_ctlcluster 15 main start
else
    echo "PostgreSQL 15 is already running."
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
python manage.py runserver 0.0.0.0:8000