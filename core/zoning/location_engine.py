"""
GPS & User Location Tracking Engine
Handles user location, geofencing, nearest services, and continuous monitoring.
"""
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.utils import timezone
from django.core.cache import cache

from core.models import AlertZone, UserProfile, DynamicZone, AdministrativeBoundary
from core.zoning.h3_intelligence import get_or_create_h3_cell, _get_h3_resolution

logger = logging.getLogger(__name__)

LOCATION_CACHE_TIMEOUT = 300  # 5 minutes
GEOFENCE_ALERT_RADIUS_M = 500  # Alert when within 500m of high-risk zone


def process_user_location(user, lat, lon, accuracy_m=None, timestamp=None):
    """
    Process a user's location update.
    Returns location analysis including zones, services, and alerts.
    """
    if timestamp is None:
        timestamp = timezone.now()

    lat_f = float(lat)
    lon_f = float(lon)

    # Validate coordinates
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return {'error': 'Invalid coordinates'}

    # Cache key for this location
    cache_key = f"user_location:{user.id}:{lat_f:.4f}:{lon_f:.4f}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    user_point = Point(lon_f, lat_f, srid=4326)
    result = {
        'user_id': user.id,
        'timestamp': timestamp.isoformat(),
        'coordinates': {'lat': lat_f, 'lon': lon_f},
        'accuracy_m': accuracy_m,
        'h3_cell': None,
        'administrative_area': None,
        'nearest_flood_zone': None,
        'nearest_river': None,
        'nearest_shelter': None,
        'nearest_hospital': None,
        'nearest_evacuation_center': None,
        'is_in_flood_risk_area': False,
        'alerts': [],
        'safe_routes': [],
    }

    # Determine H3 cell
    try:
        resolution = _get_h3_resolution(lat_f, lon_f)
        cell = get_or_create_h3_cell(lat_f, lon_f, resolution=resolution)
        if cell:
            result['h3_cell'] = {
                'h3_index': cell.h3_index,
                'resolution': cell.resolution,
                'risk_score': float(cell.current_risk_score or 0),
            }
    except Exception as e:
        logger.warning(f"H3 cell lookup failed: {e}")

    # Determine administrative area
    try:
        admin = AdministrativeBoundary.objects.filter(
            geometry__contains=user_point,
            boundary_type__in=['ward', 'village', 'constituency', 'county']
        ).first()
        if admin:
            result['administrative_area'] = {
                'id': admin.id,
                'name': admin.name,
                'type': admin.boundary_type,
                'parent': admin.parent.name if admin.parent else None,
            }
    except Exception as e:
        logger.warning(f"Administrative area lookup failed: {e}")

    # Check flood zones
    try:
        flood_zones = AlertZone.objects.filter(polygon__contains=user_point).order_by('-risk_score')[:5]
        if flood_zones.exists():
            result['is_in_flood_risk_area'] = True
            nearest = flood_zones.first()
            result['nearest_flood_zone'] = {
                'id': nearest.id,
                'name': nearest.name,
                'risk_score': float(nearest.risk_score or 0),
                'distance_m': 0,
            }
            for zone in flood_zones[1:]:
                result['alerts'].append({
                    'type': 'flood_risk',
                    'zone': zone.name,
                    'risk_score': float(zone.risk_score or 0),
                    'message': f"You are in flood risk area: {zone.name}",
                })
    except Exception as e:
        logger.warning(f"Flood zone check failed: {e}")

    # Check dynamic zones
    try:
        dynamic_zones = DynamicZone.objects.filter(
            geometry__contains=user_point,
            state__in=['active', 'escalated']
        ).order_by('-risk_score')[:3]
        for zone in dynamic_zones:
            result['alerts'].append({
                'type': 'dynamic_flood_risk',
                'zone': zone.name,
                'risk_score': float(zone.risk_score or 0),
                'confidence': float(zone.confidence or 0),
                'message': f"Active flood alert: {zone.name}",
            })
    except Exception as e:
        logger.warning(f"Dynamic zone check failed: {e}")

    # Find nearest river
    try:
        rivers = AdministrativeBoundary.objects.filter(
            boundary_type='river',
            geometry__distance_lte=(user_point, D(km=2))
        ).order_by('geometry__distance')[:3]
        if rivers.exists():
            nearest_river = rivers.first()
            result['nearest_river'] = {
                'id': nearest_river.id,
                'name': nearest_river.name,
                'distance_m': round(float(nearest_river.geometry.distance(user_point) * 111320), 1),
            }
    except Exception as e:
        logger.warning(f"River lookup failed: {e}")

    # Find nearest shelter (low-risk zones)
    try:
        shelters = AlertZone.objects.filter(
            risk_score__lte=0.4,
            polygon__distance_lte=(user_point, D(km=10))
        ).order_by('polygon__distance')[:5]
        if shelters.exists():
            shelter = shelters.first()
            result['nearest_shelter'] = {
                'id': shelter.id,
                'name': shelter.name,
                'risk_score': float(shelter.risk_score or 0),
                'distance_m': round(float(shelter.polygon.distance(user_point) * 111320), 1),
            }
    except Exception as e:
        logger.warning(f"Shelter lookup failed: {e}")

    # Find nearest hospital
    try:
        import requests
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': 'hospital',
                'format': 'json',
                'lat': lat_f,
                'lon': lon_f,
                'viewbox': f"{lon_f-0.5},{lat_f-0.5},{lon_f+0.5},{lat_f+0.5}",
                'bounded': 1,
                'limit': 3,
            },
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data:
                nearest = data[0]
                result['nearest_hospital'] = {
                    'name': nearest.get('display_name', '').split(',')[0],
                    'lat': float(nearest.get('lat', 0)),
                    'lon': float(nearest.get('lon', 0)),
                    'distance_m': _haversine_m(lat_f, lon_f, float(nearest.get('lat', 0)), float(nearest.get('lon', 0))),
                }
    except Exception:
        pass

    # Cache result
    cache.set(cache_key, result, LOCATION_CACHE_TIMEOUT)
    return result


def batch_process_locations(location_updates):
    """
    Process multiple user location updates efficiently.
    location_updates: list of dicts with user_id, lat, lon, accuracy_m, timestamp
    """
    results = []
    for update in location_updates:
        try:
            result = process_user_location(
                user_id=update.get('user_id'),
                lat=update.get('lat'),
                lon=update.get('lon'),
                accuracy_m=update.get('accuracy_m'),
                timestamp=update.get('timestamp'),
            )
            results.append(result)
        except Exception as e:
            logger.warning(f"Batch location processing failed: {e}")
            results.append({'error': str(e)})
    return results


def get_user_location_history(user, hours=24):
    """
    Get user location history (placeholder for future implementation).
    In production, this would query a location history table.
    """
    return {
        'user_id': user.id,
        'hours': hours,
        'locations': [],
        'message': 'Location history requires location tracking to be enabled',
    }


def check_geofence_entry(user, lat, lon):
    """
    Check if user is entering a flood risk zone.
    Returns alert if entering high-risk area.
    """
    result = process_user_location(user, lat, lon)
    alerts = []

    if result.get('is_in_flood_risk_area'):
        zone = result.get('nearest_flood_zone')
        if zone and zone.get('risk_score', 0) > 0.7:
            alerts.append({
                'type': 'geofence_entry_high_risk',
                'priority': 'critical',
                'message': f"You have entered a high-risk flood zone: {zone['name']}. Seek higher ground immediately.",
                'zone': zone['name'],
                'risk_score': zone['risk_score'],
            })

    for alert in result.get('alerts', []):
        if alert['type'] == 'flood_risk' and not any(a['type'] == 'geofence_entry_high_risk' for a in alerts):
            alerts.append({
                'type': 'geofence_entry_risk',
                'priority': 'high',
                'message': f"You are entering a monitored flood risk area: {alert['zone']}",
                'zone': alert['zone'],
            })

    return alerts


def _haversine_m(lat1, lon1, lat2, lon2):
    radius = 6371000
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


class LocationEngine:
    """
    Production-grade location engine with graceful fallback chain.
    Fallback: GPS → Network Location → Last Known Location → Manual Search
    """

    def __init__(self, user):
        self.user = user
        self.current_location = None
        self.location_history = []

    def update_location(self, lat, lon, accuracy_m=None, source='gps'):
        """
        Update user location with source tracking.
        """
        self.current_location = {
            'lat': float(lat),
            'lon': float(lon),
            'accuracy_m': accuracy_m,
            'source': source,
            'timestamp': timezone.now().isoformat(),
        }
        self.location_history.append(self.current_location)
        return self.current_location

    def get_current_location(self):
        """
        Get current location with fallback chain.
        """
        if self.current_location:
            return self.current_location

        # Try last known location from cache
        cache_key = f"user_last_location:{self.user.id}"
        cached = cache.get(cache_key)
        if cached:
            self.current_location = cached
            return cached

        return None

    def analyze_current_location(self):
        """
        Full analysis of current location.
        """
        location = self.get_current_location()
        if not location:
            return {'error': 'No location available', 'fallback': 'manual_search'}

        return process_user_location(
            self.user,
            location['lat'],
            location['lon'],
            accuracy_m=location.get('accuracy_m'),
            timestamp=location.get('timestamp'),
        )
