"""
Management command to perform system health check.
Checks database, redis, celery, and model integrity.
"""

from django.core.management.base import BaseCommand
from django.db import connection, connections
from django.conf import settings
from core.models import AlertZone, FloodReading, IncidentReport
import redis
from celery import current_app as celery_app


class Command(BaseCommand):
    help = 'Perform system health check and report status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed status for each component',
        )

    def handle(self, *args, **options):
        verbose = options['verbose']
        self.stdout.write(self.style.MIGRATE_HEADING('FloodGuard Health Check'))
        self.stdout.write('')
        
        all_ok = True
        
        # Check database
        self.stdout.write('Checking database...')
        try:
            with connections['default'].cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result and result[0] == 1:
                    self.stdout.write(self.style.SUCCESS('  ✓ PostgreSQL connection OK'))
                    if verbose:
                        self.stdout.write(f'    Database: {settings.DATABASES["default"]["NAME"]}')
                        self.stdout.write(f'    Host: {settings.DATABASES["default"]["HOST"]}')
                else:
                    self.stdout.write(self.style.ERROR('  ✗ Database returned unexpected result'))
                    all_ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Database connection failed: {e}'))
            all_ok = False
        
        # Check PostGIS
        self.stdout.write('Checking PostGIS extension...')
        try:
            with connections['default'].cursor() as cursor:
                cursor.execute("SELECT PostGIS_Version()")
                result = cursor.fetchone()
                if result:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ PostGIS version: {result[0]}'))
                else:
                    self.stdout.write(self.style.WARNING('  ? PostGIS not available'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ PostGIS check failed: {e}'))
            all_ok = False
        
        # Check Redis
        self.stdout.write('Checking Redis...')
        try:
            from core.tasks import redis_client
            if redis_client.ping():
                self.stdout.write(self.style.SUCCESS('  ✓ Redis connection OK'))
                if verbose:
                    info = redis_client.info()
                    self.stdout.write(f'    Version: {info.get("redis_version", "unknown")}')
                    self.stdout.write(f'    Connected clients: {info.get("connected_clients", 0)}')
            else:
                self.stdout.write(self.style.ERROR('  ✗ Redis ping failed'))
                all_ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Redis connection failed: {e}'))
            all_ok = False
        
        # Check Celery
        self.stdout.write('Checking Celery...')
        try:
            inspect = celery_app.control.inspect()
            active = inspect.active()
            if active:
                worker_count = len(active)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Celery workers active: {worker_count}'))
                if verbose:
                    for worker, tasks in active.items():
                        self.stdout.write(f'    {worker}: {len(tasks)} tasks')
            else:
                self.stdout.write(self.style.WARNING('  ! No active Celery workers (may be idle)'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Celery check failed: {e}'))
            all_ok = False
        
        # Check ML model
        self.stdout.write('Checking ML model...')
        import os
        model_path = settings.FLOOD_MODEL_PATH
        if os.path.exists(model_path):
            size_mb = os.path.getsize(model_path) / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(f'  ✓ ML model found ({size_mb:.2f} MB)'))
            try:
                import joblib
                model = joblib.load(model_path)
                self.stdout.write(f'    Model type: {type(model).__name__}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  ! Model file exists but failed to load: {e}'))
        else:
            self.stdout.write(self.style.ERROR(f'  ✗ ML model not found at {model_path}'))
            all_ok = False
        
        # Check database content counts
        self.stdout.write('Checking database content...')
        try:
            zones_count = AlertZone.objects.count()
            readings_count = FloodReading.objects.count()
            reports_count = IncidentReport.objects.count()
            self.stdout.write(self.style.SUCCESS('  ✓ Database records:'))
            self.stdout.write(f'    Alert Zones: {zones_count}')
            self.stdout.write(f'    Flood Readings: {readings_count}')
            self.stdout.write(f'    Incident Reports: {reports_count}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Database query failed: {e}'))
            all_ok = False
        
        # Summary
        self.stdout.write('')
        if all_ok:
            self.stdout.write(self.style.SUCCESS('All systems operational ✓'))
        else:
            self.stdout.write(self.style.ERROR('Some checks failed. Review errors above.'))
            return 1
        
        return 0
