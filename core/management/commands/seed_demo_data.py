from django.contrib.gis.geos import Point, Polygon
from django.core.management.base import BaseCommand

from core.models import AlertLog, AlertZone, FloodReading


class Command(BaseCommand):
    help = 'Create demo zones, readings, and alerts for local UI verification.'

    def handle(self, *args, **options):
        demo_zones = [
            {
                'name': 'Westlands',
                'coords': [(36.80, -1.28), (36.84, -1.28), (36.84, -1.25), (36.80, -1.25), (36.80, -1.28)],
                'risk_threshold': 0.6,
                'risk_score': 0.82,
                'water_level': 3.2,
                'reading': Point(36.82, -1.265, srid=4326),
                'alert': 'High flood risk in Westlands. Avoid low-lying roads and monitor official updates.',
            },
            {
                'name': 'South B',
                'coords': [(36.82, -1.32), (36.86, -1.32), (36.86, -1.29), (36.82, -1.29), (36.82, -1.32)],
                'risk_threshold': 0.6,
                'risk_score': 0.45,
                'water_level': 1.8,
                'reading': Point(36.84, -1.305, srid=4326),
                'alert': 'Moderate flood watch for South B. Response teams are monitoring water levels.',
            },
            {
                'name': 'Kibera',
                'coords': [(36.77, -1.32), (36.81, -1.32), (36.81, -1.29), (36.77, -1.29), (36.77, -1.32)],
                'risk_threshold': 0.6,
                'risk_score': 0.25,
                'water_level': 0.7,
                'reading': Point(36.79, -1.305, srid=4326),
                'alert': '',
            },
        ]

        created_zones = 0
        created_readings = 0
        created_alerts = 0

        for item in demo_zones:
            zone, was_created = AlertZone.objects.update_or_create(
                name=item['name'],
                defaults={
                    'polygon': Polygon(item['coords'], srid=4326),
                    'risk_threshold': item['risk_threshold'],
                    'risk_score': item['risk_score'],
                },
            )
            created_zones += int(was_created)

            if not FloodReading.objects.filter(location=item['reading'], source='demo_seed').exists():
                FloodReading.objects.create(
                    location=item['reading'],
                    water_level_metres=item['water_level'],
                    risk_score=item['risk_score'],
                    source='demo_seed',
                    verified=True,
                )
                created_readings += 1

            if item['alert'] and not AlertLog.objects.filter(alert_zone=zone, message=item['alert']).exists():
                AlertLog.objects.create(
                    alert_zone=zone,
                    message=item['alert'],
                    channel='Dashboard',
                    recipient_count=0,
                    delivery_status='sent',
                )
                created_alerts += 1

        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready: {AlertZone.objects.count()} zones, '
            f'{created_readings} new readings, {created_alerts} new alerts '
            f'({created_zones} zones newly created).'
        ))
