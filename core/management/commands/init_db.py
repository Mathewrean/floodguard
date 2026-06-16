from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User, Group
from django.contrib.gis.geos import Point, Polygon
from core.models import AlertZone, FloodReading, UserProfile
from core.analytics.scoring import calculate_risk_score
from core.data_sources.aggregator import build_risk_feature_vector
import logging

logger = logging.getLogger(__name__)

NAIROBI_LOCATIONS = [
    {"name": "Westlands", "lat": -1.2636, "lon": 36.8028, "floor": 8.0},
    {"name": "South B", "lat": -1.3142, "lon": 36.8336, "floor": 6.0},
    {"name": "Kibera", "lat": -1.3143, "lon": 36.7846, "floor": 12.0},
    {"name": "Mathare", "lat": -1.2589, "lon": 36.8614, "floor": 15.0},
    {"name": "Karen", "lat": -1.3280, "lon": 36.7072, "floor": 3.0},
    {"name": "Eastleigh", "lat": -1.2756, "lon": 36.8503, "floor": 7.0},
    {"name": "Ruiru", "lat": -1.1461, "lon": 36.9572, "floor": 5.0},
    {"name": "Athi River", "lat": -1.4572, "lon": 36.9783, "floor": 25.0},
]


class Command(BaseCommand):
    help = 'Initialise database with real flood zone data from Open-Meteo API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-confirmation',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        if not options['skip_confirmation']:
            self.stdout.write(
                self.style.WARNING(
                    'WARNING: This command will delete ALL AlertZone, FloodReading, IncidentReport, and AlertLog records.\n'
                    'Superuser accounts will be preserved.\n\n'
                    'To proceed, run again with --skip-confirmation flag.'
                )
            )
            return

        with transaction.atomic():
            # STEP 1 — Purge all existing poor-quality seed data
            deleted_counts = {}
            
            # Import models that might not be available in all contexts
            try:
                from core.models import IncidentReport, AlertLog
                deleted_counts['alert_logs'] = AlertLog.objects.all().delete()[0]
                deleted_counts['incident_reports'] = IncidentReport.objects.all().delete()[0]
            except ImportError:
                deleted_counts['alert_logs'] = 0
                deleted_counts['incident_reports'] = 0
            
            deleted_counts['flood_readings'] = FloodReading.objects.all().delete()[0]
            deleted_counts['alert_zones'] = AlertZone.objects.all().delete()[0]
            
            self.stdout.write(
                self.style.SUCCESS('Deleted existing data:') +
                f"  AlertZone: {deleted_counts['alert_zones']}" +
                f"  FloodReading: {deleted_counts['flood_readings']}" +
                f"  IncidentReport: {deleted_counts['incident_reports']}" +
                f"  AlertLog: {deleted_counts['alert_logs']}"
            )

            # STEP 2 — Pull multi-source flood intelligence where configured.
            zones_created = []
            readings_created = []

            for loc in NAIROBI_LOCATIONS:
                try:
                    self.stdout.write(f"Fetching data for {loc['name']}...")
                    features = build_risk_feature_vector(loc["lat"], loc["lon"], loc["name"])
                    discharge = max(features.get('river_discharge') or 0, loc["floor"])
                    features['river_discharge'] = discharge
                    risk_score = calculate_risk_score(features)
                    
                    # STEP 3 — Create AlertZones with clean polygon boundaries
                    delta = 0.015  # half-width in degrees
                    polygon = Polygon([
                        (loc["lon"] - delta, loc["lat"] - delta),
                        (loc["lon"] + delta, loc["lat"] - delta),
                        (loc["lon"] + delta, loc["lat"] + delta),
                        (loc["lon"] - delta, loc["lat"] + delta),
                        (loc["lon"] - delta, loc["lat"] - delta)
                    ], srid=4326)
                    
                    zone = AlertZone.objects.create(
                        name=loc["name"],
                        polygon=polygon,
                        risk_score=round(risk_score, 3),
                        risk_threshold=0.65
                    )
                    zones_created.append(zone)
                    
                    reading = FloodReading.objects.create(
                        location=Point(loc["lon"], loc["lat"], srid=4326),
                        water_level_metres=round(discharge / 100.0, 2),
                        risk_score=round(risk_score, 3),
                        source='multi_source',
                        verified=features.get('sources_available', 0) > 0,
                        metadata=features,
                    )
                    readings_created.append(reading)
                    
                    self.stdout.write(
                        f"  Created {loc['name']}: discharge={discharge:.2f} m3/s, risk_score={risk_score:.3f}"
                    )
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Failed to process {loc['name']}: {str(e)}")
                    )
                    continue

            # STEP 5 — Create EmergencyTeam user for testing if not exists
            group, _ = Group.objects.get_or_create(name='EmergencyTeam')
            if not User.objects.filter(username='responder').exists():
                responder = User.objects.create_user(
                    username='responder',
                    password='responder123',
                    email='responder@floodguard.ke',
                    first_name='Jane',
                    last_name='Wanjiku'
                )
                responder.groups.add(group)
                UserProfile.objects.update_or_create(
                    user=responder,
                    defaults={
                        'role': 'authority',
                        'phone_number': '+254712345678'
                    }
                )
                self.stdout.write(
                    self.style.SUCCESS('Created test responder user: responder / responder123')
                )

            # Create admin user if not exists
            if not User.objects.filter(username='admin').exists():
                admin_user = User.objects.create_superuser(
                    username='admin',
                    password='admin123',
                    email='admin@floodguard.ke',
                    first_name='Admin',
                    last_name='User'
                )
                UserProfile.objects.update_or_create(
                    user=admin_user,
                    defaults={
                        'role': 'admin',
                        'phone_number': '+254700000000'
                    }
                )
                self.stdout.write(
                    self.style.SUCCESS('Created admin user: admin / admin123')
                )

            # Create citizen test user if not exists
            if not User.objects.filter(username='citizen').exists():
                citizen = User.objects.create_user(
                    username='citizen',
                    password='citizen123',
                    email='citizen@floodguard.ke',
                    first_name='John',
                    last_name='Otieno'
                )
                UserProfile.objects.update_or_create(
                    user=citizen,
                    defaults={
                        'role': 'citizen',
                        'phone_number': '+254711111111'
                    }
                )
                self.stdout.write(
                    self.style.SUCCESS('Created citizen user: citizen / citizen123')
                )

        # STEP 6 — Print startup summary table
        high_risk_count = AlertZone.objects.filter(risk_score__gt=0.7).count()
        
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS('┌─────────────────────────────────────────────┐'))
        self.stdout.write(self.style.SUCCESS('│  FloodGuard Development Database Ready       │'))
        self.stdout.write(self.style.SUCCESS('├─────────────────────────┬───────────────────┤'))
        self.stdout.write(self.style.SUCCESS(f'│  Alert Zones Created    │  {len(zones_created):<13} │'))
        self.stdout.write(self.style.SUCCESS(f'│  Flood Readings Created │  {len(readings_created):<13} │'))
        self.stdout.write(self.style.SUCCESS(f'│  High Risk Zones        │  {high_risk_count:<13} │'))
        self.stdout.write(self.style.SUCCESS('│  Test Users Available   │  admin/responder/citizen │'))
        self.stdout.write(self.style.SUCCESS('└─────────────────────────┴───────────────────┘'))
