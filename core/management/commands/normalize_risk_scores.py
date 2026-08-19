"""Repair historical risk scores that predate the canonical 0.0–1.0 contract."""

from datetime import timedelta

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from core.models import AlertZone, DynamicZone, FloodReading, H3Cell
from core.zoning.h3_intelligence import normalize_risk_score


class Command(BaseCommand):
    help = 'Preview or repair invalid and stale risk values without deleting operational records.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Persist the displayed repairs.')
        parser.add_argument(
            '--stale-after-minutes', type=int, default=60,
            help='Set stale H3 cell scores to zero after this age (default: 60).',
        )

    def handle(self, *args, **options):
        tables = connection.introspection.table_names()
        required = [model._meta.db_table for model in (AlertZone, DynamicZone, FloodReading, H3Cell)]
        if any(table not in tables for table in required):
            raise CommandError('The database schema has not been migrated. Run "python manage.py migrate --noinput" first.')

        stale_after = options['stale_after_minutes']
        if stale_after < 0:
            raise CommandError('--stale-after-minutes must be zero or greater.')
        stale_before = timezone.now() - timedelta(minutes=stale_after)
        model_sets = (
            ('AlertZone', AlertZone.objects.filter(risk_score__gt=1)),
            ('DynamicZone', DynamicZone.objects.filter(risk_score__gt=1)),
            ('FloodReading', FloodReading.objects.filter(risk_score__gt=1)),
            ('H3Cell', H3Cell.objects.filter(current_risk_score__gt=1)),
        )
        invalid = {name: queryset.count() for name, queryset in model_sets}
        stale_cells = H3Cell.objects.filter(last_updated__lt=stale_before, current_risk_score__gt=0)
        self.stdout.write(f'Invalid percentage-style scores: {invalid}; stale H3 cells: {stale_cells.count()}.')

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Preview only; no data changed. Rerun with --apply after review.'))
            return

        repaired = {name: 0 for name, _ in model_sets}
        with transaction.atomic():
            for name, queryset in model_sets:
                field = 'current_risk_score' if name == 'H3Cell' else 'risk_score'
                for record in queryset.iterator():
                    setattr(record, field, normalize_risk_score(getattr(record, field)))
                    record.save(update_fields=[field])
                    if name == 'H3Cell':
                        cache.delete(f'h3:{record.h3_index}:risk_score')
                    repaired[name] += 1

            stale_count = 0
            for cell in stale_cells.iterator():
                cell.current_risk_score = 0.0
                cell.save(update_fields=['current_risk_score'])
                cache.delete(f'h3:{cell.h3_index}:risk_score')
                stale_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Repaired {repaired}; cleared {stale_count} stale H3 cell score(s).'
        ))
