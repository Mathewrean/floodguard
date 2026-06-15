# Multi-stage Dockerfile for FloodGuard Production
# Stage 1: Build dependencies and collect static files
# Cache-buster: 2026-06-15 - libgdal32 fix
FROM python:3.13-slim-bookworm as builder

WORKDIR /app

# Install system dependencies for GDAL, PostGIS, and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    postgresql-client \
    libpq-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    cargo \
    libjpeg-dev \
    zlib1g-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Production runtime image
FROM python:3.13-slim-bookworm

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home appuser && \
    mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R appuser:appuser /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal32 \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    libwebp7 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Ensure PYTHONPATH picks up user-installed packages
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy project code
# Cache-buster: 2026-06-15-2 - settings fix
COPY --chown=appuser:appuser . /app

# Switch to non-root user
USER appuser

# Environment defaults (override via environment variables)
ENV DEBUG=False \
    DB_NAME=floodguard \
    DB_USER=postgres \
    DB_PASSWORD="" \
    DB_HOST=db \
    DB_PORT=5432

# Collect static files (will be overridden by entrypoint if needed)
RUN python manage.py collectstatic --noinput --clear || true

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python manage.py health_check || exit 1

# Use gunicorn with gevent for async support
CMD ["gunicorn", "floodguard.asgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
