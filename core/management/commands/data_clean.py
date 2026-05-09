from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile, User
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean all seeded/test data from the database while preserving superusers and essential system data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-users',
            action='store_true',
            help='Keep regular user accounts (only delete anonymous/test users)',
        )
        parser.add_argument(
            '--keep-sessions',
            action='store_true',
            help='Keep session data',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        if not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    'WARNING: This command will delete ALL data except superusers.\n'
                    'This includes alert zones, flood readings, incident reports, alert logs, user profiles,\n'
                    'and (unless --keep-users is specified) all non-superuser accounts.\n\n'
                    'To proceed, run again with --force flag.'
                )
            )
            return

        with transaction.atomic():
            # Delete in order respecting foreign key constraints
            deleted_counts = {}
            
            # Alert logs (depends on alert zones)
            deleted_counts['alert_logs'] = AlertLog.objects.all().delete()[0]
            
            # Incident reports (may depend on users)
            deleted_counts['incident_reports'] = IncidentReport.objects.all().delete()[0]
            
            # Flood readings
            deleted_counts['flood_readings'] = FloodReading.objects.all().delete()[0]
            
            # Alert zones
            deleted_counts['alert_zones'] = AlertZone.objects.all().delete()[0]
            
            # User profiles (depends on users)
            deleted_counts['user_profiles'] = UserProfile.objects.all().delete()[0]
            
            # Users (except superusers)
            if not options['keep_users']:
                deleted_counts['users'] = User.objects.filter(is_superuser=False).delete()[0]
            else:
                # Only delete anonymous/test users
                deleted_counts['users'] = User.objects.filter(
                    is_superuser=False,
                    username__startswith='test'
                ).delete()[0]

            # Clean up any orphaned related data
            # (This would be model-specific based on your actual relationships)

        # Report results
        self.stdout.write(self.style.SUCCESS('Data cleanup completed successfully:'))
        for model, count in deleted_counts.items():
            self.stdout.write(f'  - {model}: {count} records deleted')

        if options['keep_users']:
            self.stdout.write(
                self.style.NOTICE(
                    'Note: Regular user accounts were preserved per --keep-users flag. '
                    'Only test users (username starting with "test") were removed.'
                )
            )