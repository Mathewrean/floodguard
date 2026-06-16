web: DJANGO_SETTINGS_MODULE=floodguard.settings_production daphne -b 0.0.0.0 -p $PORT floodguard.asgi:application
worker: DJANGO_SETTINGS_MODULE=floodguard.settings_production celery -A floodguard worker --loglevel=warning --without-gossip --without-mingle
beat: DJANGO_SETTINGS_MODULE=floodguard.settings_production celery -A floodguard beat --loglevel=warning --schedule=/tmp/celerybeat-schedule
