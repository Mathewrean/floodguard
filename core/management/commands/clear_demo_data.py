from django.core.management.base import BaseCommand

from core.models import AlertLog, AlertZone, FloodReading, IncidentReport


class Command(BaseCommand):
    help = 'Clear current/demo operational data without deleting users or permissions.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Confirm deletion without an interactive prompt.',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            self.stdout.write('This deletes AlertLog, FloodReading, IncidentReport, and AlertZone rows.')
            confirm = input('Type CLEAR to continue: ')
            if confirm != 'CLEAR':
                self.stdout.write(self.style.WARNING('Aborted.'))
                return

        counts = {
            'alerts': AlertLog.objects.count(),
            'readings': FloodReading.objects.count(),
            'reports': IncidentReport.objects.count(),
            'zones': AlertZone.objects.count(),
        }

        AlertLog.objects.all().delete()
        FloodReading.objects.all().delete()
        IncidentReport.objects.all().delete()
        AlertZone.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(
            'Cleared current data: '
            f"{counts['alerts']} alerts, {counts['readings']} readings, "
            f"{counts['reports']} reports, {counts['zones']} zones."
        ))
