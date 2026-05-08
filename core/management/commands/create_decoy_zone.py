"""Management command to create a decoy/test zone for manual QA testing."""

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Polygon
from core.models import AlertZone


class Command(BaseCommand):
    help = "Create a decoy/test flood zone for QA and demonstration purposes"

    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            type=str,
            default='Test Zone - Demo',
            help='Name for the decoy zone'
        )
        parser.add_argument(
            '--risk',
            type=float,
            default=0.65,
            help='Initial risk score (0.0-1.0)'
        )
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.5,
            help='Alert threshold (0.0-1.0)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force creation even if zone with same name exists'
        )

    def handle(self, *args, **options):
        name = options['name']
        risk = max(0.0, min(1.0, options['risk']))
        threshold = max(0.0, min(1.0, options['threshold']))

        # Check for existing zone with same name
        if AlertZone.objects.filter(name=name).exists() and not options['force']:
            self.stdout.write(self.style.WARNING(
                f"Zone '{name}' already exists. Use --force to recreate."
            ))
            return

        # Create a small decoy polygon within Kenya/East Africa bounds
        # Centered roughly near Nairobi but offset for testing
        test_polygon = Polygon([
            (36.85, -1.25),   # SW corner
            (36.95, -1.25),   # SE corner
            (36.95, -1.15),   # NE corner
            (36.85, -1.15),   # NW corner
            (36.85, -1.25)    # Close loop
        ], srid=4326)

        zone = AlertZone.objects.create(
            name=name,
            polygon=test_polygon,
            risk_threshold=threshold,
            risk_score=risk,
            manual_override_active=False
        )

        self.stdout.write(self.style.SUCCESS(
            f"✓ Created decoy zone '{zone.name}' (ID: {zone.id})\n"
            f"  • Polygon: SW(36.85,-1.25) → NE(36.95,-1.15)\n"
            f"  • Risk Score: {zone.risk_score:.2%}\n"
            f"  • Threshold: {zone.risk_threshold:.2%}\n"
            f"  • Centroid: {zone.polygon.centroid.coords}\n"
            f"\nView on admin: /admin/core/alertzone/{zone.id}/change/"
        ))
