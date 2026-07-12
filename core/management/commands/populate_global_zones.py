from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.gis.geos import Point, Polygon
from core.models import AlertZone, FloodReading
import logging

logger = logging.getLogger(__name__)

# 15+ major world cities/zones prone to flooding, spanning all continents
GLOBAL_ZONES = [
    {"name": "Dhaka", "lat": 23.8103, "lon": 90.4125, "country": "Bangladesh"},
    {"name": "Jakarta", "lat": -6.2088, "lon": 106.8456, "country": "Indonesia"},
    {"name": "Manila", "lat": 14.5995, "lon": 120.9842, "country": "Philippines"},
    {"name": "Lagos", "lat": 6.5244, "lon": 3.3792, "country": "Nigeria"},
    {"name": "Cairo", "lat": 30.0444, "lon": 31.2357, "country": "Egypt"},
    {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777, "country": "India"},
    {"name": "Karachi", "lat": 24.8607, "lon": 67.0011, "country": "Pakistan"},
    {"name": "Buenos Aires", "lat": -34.6037, "lon": -58.3816, "country": "Argentina"},
    {"name": "London", "lat": 51.5074, "lon": -0.1278, "country": "United Kingdom"},
    {"name": "New York", "lat": 40.7128, "lon": -74.0060, "country": "USA"},
    {"name": "Shanghai", "lat": 31.2304, "lon": 121.4737, "country": "China"},
    {"name": "Bangkok", "lat": 13.7563, "lon": 100.5018, "country": "Thailand"},
    {"name": "Sao Paulo", "lat": -23.5505, "lon": -46.6333, "country": "Brazil"},
    {"name": "Nairobi", "lat": -1.2921, "lon": 36.8219, "country": "Kenya"},
    {"name": "Cape Town", "lat": -33.9249, "lon": 18.4241, "country": "South Africa"},
    {"name": "Tokyo", "lat": 35.6762, "lon": 139.6503, "country": "Japan"},
    {"name": "Miami", "lat": 25.7617, "lon": -80.1918, "country": "USA"},
    {"name": "Amsterdam", "lat": 52.3676, "lon": 4.9041, "country": "Netherlands"},
]


class Command(BaseCommand):
    help = 'Populate database with global flood risk zones for worldwide coverage (STATIC - use sync_zones_from_activity for dynamic)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-confirmation',
            action='store_true',
            help='Skip confirmation prompt',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing zones before seeding',
        )

    def handle(self, *args, **options):
        if not options['skip_confirmation']:
            self.stdout.write(
                self.style.WARNING(
                    'WARNING: This command will populate AlertZone and FloodReading records.\n'
                    'Use --clear to delete existing records first.\n\n'
                    'To proceed, run again with --skip-confirmation flag.'
                )
            )
            return

        with transaction.atomic():
            if options['clear']:
                self.stdout.write('Clearing existing data...')
                FloodReading.objects.all().delete()
                AlertZone.objects.all().delete()
                self.stdout.write(self.style.SUCCESS('Cleared existing zones and readings'))

            zones_created = 0
            readings_created = 0

            for loc in GLOBAL_ZONES:
                try:
                    zone_name = f"{loc['name']} - {loc['country']}"
                    
                    # Create a polygon ~20km x 20km around the city center
                    delta_lat = 0.09  # ~10km
                    delta_lon = 0.09 / max(0.5, abs(loc['lat'] / 90.0))
                    polygon = Polygon([
                        (loc["lon"] - delta_lon, loc["lat"] - delta_lat),
                        (loc["lon"] + delta_lon, loc["lat"] - delta_lat),
                        (loc["lon"] + delta_lon, loc["lat"] + delta_lat),
                        (loc["lon"] - delta_lon, loc["lat"] + delta_lat),
                        (loc["lon"] - delta_lon, loc["lat"] - delta_lat)
                    ], srid=4326)
                    
                    zone, created = AlertZone.objects.get_or_create(
                        name=zone_name,
                        defaults={
                            'polygon': polygon,
                            'risk_score': 0.1,
                            'risk_threshold': 0.65,
                        }
                    )
                    
                    if created:
                        zones_created += 1
                        
                        # Create an initial flood reading at the city center
                        reading = FloodReading.objects.create(
                            location=Point(loc["lon"], loc["lat"], srid=4326),
                            water_level_metres=0.0,
                            risk_score=0.1,
                            source='global_seed',
                            verified=False,
                            metadata={
                                'city': loc['name'],
                                'country': loc['country'],
                                'source': 'global_seed',
                            }
                        )
                        readings_created += 1
                        
                        self.stdout.write(
                            f"  Created {zone_name}: lat={loc['lat']}, lon={loc['lon']}"
                        )
                    else:
                        self.stdout.write(f"  Skipped {zone_name} (already exists)")
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Failed to create {loc['name']}: {str(e)}")
                    )
                    continue

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS('┌─────────────────────────────────────────────┐'))
            self.stdout.write(self.style.SUCCESS('│  Global Flood Zones Populated               │'))
            self.stdout.write(self.style.SUCCESS('├─────────────────────────┬───────────────────┤'))
            self.stdout.write(self.style.SUCCESS(f'│  Zones Created          │  {zones_created:<13} │'))
            self.stdout.write(self.style.SUCCESS(f'│  Readings Created       │  {readings_created:<13} │'))
            self.stdout.write(self.style.SUCCESS(f'│  Total Zones            │  {AlertZone.objects.count():<13} │'))
            self.stdout.write(self.style.SUCCESS('└─────────────────────────┴───────────────────┘'))
