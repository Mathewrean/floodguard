web: daphne -b 0.0.0.0 -p $PORT floodguard.asgi:application
worker: celery -A floodguard worker --loglevel=warning
beat: celery -A floodguard beat --loglevel=warning
