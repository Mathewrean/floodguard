import warnings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.core.cache import cache
from core.models import AlertZone, FloodReading, IncidentReport
import os
from celery import current_app as celery_app

# Force silence scikit-learn unpickling warnings globally
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

class Command(BaseCommand):
    help = 'Perform system health check and report status'

    def handle(self, *args, **options):
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
                else:
                    self.stdout.write(self.style.ERROR('  ✗ Database failed'))
                    all_ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Database failed: {e}'))
            all_ok = False

        # Check PostGIS
        self.stdout.write('Checking PostGIS extension...')
        try:
            with connections['default'].cursor() as cursor:
                cursor.execute("SELECT PostGIS_Version()")
                result = cursor.fetchone()
                self.stdout.write(self.style.SUCCESS(f'  ✓ PostGIS version: {result[0]}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ PostGIS check failed: {e}'))
            all_ok = False

        # Check Redis via Django Cache Registry
        self.stdout.write('Checking Redis...')
        try:
            cache.set('health_check_test', 'ok', timeout=5)
            if cache.get('health_check_test') == 'ok':
                self.stdout.write(self.style.SUCCESS('  ✓ Redis connection OK'))
            else:
                self.stdout.write(self.style.ERROR('  ✗ Redis test mismatch'))
                all_ok = False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Redis connection failed: {e}'))
            all_ok = False

        # Check Celery
        self.stdout.write('Checking Celery...')
        try:
            inspect = celery_app.control.inspect()
            active = inspect.active() if inspect else None
            if active:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Celery workers active: {len(active)}'))
            else:
                self.stdout.write(self.style.WARNING('  ! No active Celery workers'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Celery check failed: {e}'))
            all_ok = False

        # Check database content counts
        self.stdout.write('Checking database content...')
        try:
            zones_count = AlertZone.objects.count()
            readings_count = FloodReading.objects.count()
            incidents_count = IncidentReport.objects.count()

            self.stdout.write(self.style.SUCCESS('  ✓ Database records read successfully:'))
            self.stdout.write(f'    Alert Zones: {zones_count}')
            self.stdout.write(f'    Flood Readings: {readings_count}')
            self.stdout.write(f'    Incident Reports: {incidents_count}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Failed to fetch data records: {e}'))
            all_ok = False

        self.stdout.write('')
        if all_ok:
            self.stdout.write(self.style.SUCCESS('ALL SYSTEMS OPERATIONAL ✓'))
            return 'Success'
        else:
            self.stdout.write(self.style.ERROR('SOME CHECKS FAILED'))
            raise CommandError('Health check failed')
