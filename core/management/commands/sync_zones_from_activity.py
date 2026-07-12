from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone
from datetime import timedelta
from core.models import AlertZone, AlertZoneActivity
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync AlertZones from recent user GPS activity. Creates/updates zones based on real user coordinates.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Look back period in hours (default: 24)',
        )
        parser.add_argument(
            '--radius',
            type=float,
            default=0.05,
            help='Cluster radius in degrees (default: 0.05, ~5km)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without making changes',
        )

    def handle(self, *args, **options):
        hours = options['hours']
        radius = options['radius']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - no changes will be made'))

        cutoff = timezone.now() - timedelta(hours=hours)
        activities = AlertZoneActivity.objects.filter(created_at__gte=cutoff).select_related('zone')

        self.stdout.write(f"Found {activities.count()} user activities in last {hours}h")

        # Group activities by location clusters
        clusters = self._cluster_activities(activities, radius)
        self.stdout.write(f"Identified {len(clusters)} location clusters")

        created = 0
        updated = 0
        skipped = 0

        for cluster in clusters:
            lat = cluster['lat']
            lon = cluster['lon']
            count = cluster['count']
            users = cluster['users']

            # Check if any existing zone covers this cluster
            point = Point(lon, lat, srid=4326)
            existing_zone = AlertZone.objects.filter(polygon__covers=point).first()

            if existing_zone:
                # Update existing zone activity
                existing_zone.checkin_count = count
                existing_zone.last_user_checkin = timezone.now()
                existing_zone.save(update_fields=['checkin_count', 'last_user_checkin', 'updated_at'])
                updated += 1
                self.stdout.write(f"  Updated: {existing_zone.name} ({count} checkins)")
            else:
                # Create new dynamic zone
                zone_name = self._name_from_cluster(lat, lon, count)
                polygon = Polygon.from_bbox((
                    lon - radius, lat - radius,
                    lon + radius, lat + radius
                ), srid=4326)

                if not dry_run:
                    zone = AlertZone.objects.create(
                        name=zone_name,
                        polygon=polygon,
                        risk_score=0.1,
                        risk_threshold=0.65,
                    )
                    created += 1
                    self.stdout.write(f"  Created: {zone_name} ({count} checkins)")
                else:
                    created += 1
                    self.stdout.write(f"  Would create: {zone_name} ({count} checkins)")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS('┌─────────────────────────────────────────────┐'))
        self.stdout.write(self.style.SUCCESS('│  Dynamic Zone Sync Complete                 │'))
        self.stdout.write(self.style.SUCCESS('├─────────────────────────┬───────────────────┤'))
        self.stdout.write(self.style.SUCCESS(f'│  Zones Created          │  {created:<13} │'))
        self.stdout.write(self.style.SUCCESS(f'│  Zones Updated          │  {updated:<13} │'))
        self.stdout.write(self.style.SUCCESS(f'│  Zones Skipped          │  {skipped:<13} │'))
        self.stdout.write(self.style.SUCCESS('└─────────────────────────┴───────────────────┘'))

    def _cluster_activities(self, activities, radius):
        """
        Group activities into clusters based on geographic proximity.
        Returns list of cluster dicts with lat, lon, count, users.
        """
        clusters = []
        used = set()

        for activity in activities:
            if activity.zone_id in used:
                continue

            # Find all activities near this one
            point = Point(activity.longitude, activity.latitude, srid=4326)
            nearby = []
            users = set()

            for other in activities:
                if other.id in used:
                    continue
                other_point = Point(other.longitude, other.latitude, srid=4326)
                if point.distance(other_point) <= radius:
                    nearby.append(other)
                    users.add(other.user_id or other.ip_address)
                    used.add(other.id)

            if nearby:
                avg_lat = sum(a.latitude for a in nearby) / len(nearby)
                avg_lon = sum(a.longitude for a in nearby) / len(nearby)
                clusters.append({
                    'lat': avg_lat,
                    'lon': avg_lon,
                    'count': len(nearby),
                    'users': users,
                })

        return clusters

    def _name_from_cluster(self, lat, lon, count):
        """Generate a human-readable name for a cluster."""
        import requests as req
        try:
            geo = req.get(
                'https://nominatim.openstreetmap.org/reverse',
                params={'lat': lat, 'lon': lon, 'format': 'json'},
                headers={'User-Agent': 'FloodGuard/1.0'},
                timeout=5,
            )
            geo.raise_for_status()
            address = geo.json().get('address', {})
            area = (
                address.get('suburb') or
                address.get('neighbourhood') or
                address.get('city_district') or
                address.get('town') or
                address.get('city')
            )
            if area:
                return f"Dynamic - {area} ({count} checkins)"[:100]
        except Exception:
            pass
        return f"Dynamic Zone {lat:.3f},{lon:.3f} ({count})"[:100]
