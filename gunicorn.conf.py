"""
Gunicorn configuration for FloodGuard production deployment.
Optimized for handling WebSocket connections via uvicorn workers.
"""

import multiprocessing
import os

# Server socket
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:8000')
backlog = 2048

# Worker processes - calculate optimal based on CPU cores
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'uvicorn.workers.UvicornWorker')
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'floodguard'

# Server mechanics
daemon = False
pidfile = None
umask = 0o022
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Graceful timeout
graceful_timeout = 30

# Preload app to reduce memory usage (but increases startup time)
# Set GUNICORN_PRELOAD=1 to enable
preload_app = os.getenv('GUNICORN_PRELOAD', '0') == '1'

# Worker lifecycle hooks
def on_starting(server):
    """Log when server starts."""
    server.log.info("FloodGuard Gunicorn server starting")

def on_exit(server):
    """Log when server exits."""
    server.log.info("FloodGuard Gunicorn server shutting down")

def worker_int(worker):
    """Handle worker interrupt (graceful shutdown)."""
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    """Handle worker abort (immediate shutdown)."""
    worker.log.info("Worker received SIGABRT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker %s spawned (pid: %s)", worker.age, worker.pid)

def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forking new master process")

def pre_request(worker, req):
    """Called just before a worker processes a request."""
    pass

def post_request(worker, req, environ, resp):
    """Called after a worker processes a request."""
    pass

def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info("Worker %s exited", worker.pid)
