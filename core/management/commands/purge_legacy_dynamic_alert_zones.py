"""Remove only the legacy AlertZone records created by GPS lookups."""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import AlertZone


class Command(BaseCommand):
    help = (
        'Preview or remove legacy AlertZone records named "Dynamic Zone ...". '
        'Use --apply to delete after reviewing the preview.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Delete the displayed legacy GPS-created zones.',
        )

    def handle(self, *args, **options):
        zones = AlertZone.objects.filter(name__startswith='Dynamic Zone').order_by('id')
        count = zones.count()
        self.stdout.write(f'Found {count} legacy dynamic AlertZone record(s).')
        for zone in zones[:50]:
            self.stdout.write(f'  #{zone.id}: {zone.name} (risk {zone.risk_score:.2f})')
        if count > 50:
            self.stdout.write(f'  ... and {count - 50} more')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                'Preview only; no data changed. Review this list, then rerun with --apply to delete it.'
            ))
            return

        with transaction.atomic():
            deleted, _ = zones.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Removed {count} legacy dynamic zone(s) ({deleted} related row(s) deleted by database cascade).'
        ))
