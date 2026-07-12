web: gunicorn floodguard.asgi:application \
  -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:$PORT
worker: celery -A floodguard worker --loglevel=warning
beat: celery -A floodguard beat --loglevel=warning
