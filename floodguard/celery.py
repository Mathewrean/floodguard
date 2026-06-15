import os
from celery import Celery
from celery.signals import worker_ready, worker_shutdown

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'floodguard.settings')

app = Celery('floodguard')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

@worker_ready.connect
def on_worker_ready(sender=app, **kwargs):
    print("Celery worker is ready")