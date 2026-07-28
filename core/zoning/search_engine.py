"""
Universal Location Search Engine
Supports search by coordinates, place names, OSM features, administrative hierarchy.
"""
import logging
import re
import requests

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.conf import settings
from django.core.cache import cache

from core.models import AlertZone, DynamicZone, AdministrativeBoundary, FloodReading
from core.zoning.h3_intelligence import get_or_create_h3_cell, _get_h3_resolution

logger = logging.getLogger(__name__)

SEARCH_CACHE_TIMEOUT = 600  # 10 minutes


def _is_osm_feature_query(query):
    feature_keywords = ['hospital', 'school', 'police', 'fire', 'river', 'lake', 'market', 'bridge', 'road']
    return any(kw in query.lower() for kw in feature_keywords)


def universal_search(query, user=None, lat=None, lon=None, radius_km=50):
    """
    Universal search for flood-related information.
    
    Supports:
    - GPS coordinates (lat,lon)
    - Place names (city, village, ward, etc.)
    - OSM features (hospital, school, river, etc.)
    - Administrative hierarchy
    
    Returns structured JSON with all relevant information.
    """
    cache_key = f"search:{hash(query)}:{lat}:{lon}:{radius_km}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = {
        'query': query,
        'type': 'unknown',
        'location': None,
        'weather': None,
        'flood_risk': None,
        'prediction': None,
        'nearby_shelters': [],
        'nearby_hospitals': [],
        'nearby_police': [],
        'nearby_fire_stations': [],
        'safe_routes': [],
        'decision_support': None,
        'ai_explanation': None,
        'population_exposure': None,
        'infrastructure_exposure': None,
        'historical_flooding': None,
        'administrative_hierarchy': None,
        'h3_information': None,
    }

    # Detect query type
    if lat and lon:
        result['type'] = 'coordinates'
        result['location'] = _search_by_coordinates(float(lat), float(lon), radius_km)
    elif _is_coordinate_query(query):
        result['type'] = 'coordinates'
        lat, lon = _parse_coordinates(query)
        result['location'] = _search_by_coordinates(lat, lon, radius_km)
    elif _is_osm_feature_query(query):
        result['type'] = 'osm_feature'
        result['location'] = _search_osm_feature(query, radius_km)
    else:
        result['type'] = 'place_name'
        result['location'] = _search_by_place_name(query, radius_km)

    # Enrich with weather and risk data
    if result['location']:
        loc = result['location']
        lat = loc.get('lat') or loc.get('latitude')
        lon = loc.get('lon') or loc.get('longitude') or loc.get('lng')

        if lat and lon:
            result['weather'] = _get_weather_data(lat, lon)
            result['flood_risk'] = _get_flood_risk(lat, lon)
            result['prediction'] = _get_prediction(lat, lon)
            result['nearby_shelters'] = _find_nearby_shelters(lat, lon, radius_km)
            result['nearby_hospitals'] = _find_nearby_hospitals(lat, lon, radius_km)
            result['nearby_police'] = _find_nearby_police(lat, lon, radius_km)
            result['nearby_fire_stations'] = _find_nearby_fire_stations(lat, lon, radius_km)
            result['safe_routes'] = _get_safe_routes(lat, lon)
            result['decision_support'] = _generate_decision_support(lat, lon, result)
            result['population_exposure'] = _estimate_population_exposure(lat, lon)
            result['infrastructure_exposure'] = _estimate_infrastructure_exposure(lat, lon)
            result['historical_flooding'] = _get_historical_flooding(lat, lon)
            result['administrative_hierarchy'] = _get_administrative_hierarchy(lat, lon)
            result['h3_information'] = _get_h3_information(lat, lon)

    cache.set(cache_key, result, SEARCH_CACHE_TIMEOUT)
    return result


def _is_coordinate_query(query):
    """Check if query looks like coordinates."""
    pattern = r'^-?\d+\.?\d*[,\s]+-?\d+\.?\d*$'
    return bool(re.match(pattern, query.strip()))


def _parse_coordinates(query):
    """Parse coordinates from string."""
    parts = re.split(r'[,\s]+', query.strip())
    if len(parts) >= 2:
        return float(parts[0]), float(parts[1])
    raise ValueError("Invalid coordinate format")


def _search_by_coordinates(lat, lon, radius_km):
    """Search by GPS coordinates."""
    user_point = Point(lon, lat, srid=4326)
    
    # Find nearest zone
    nearest_zone = AlertZone.objects.filter(
        polygon__distance_lte=(user_point, D(km=radius_km))
    ).order_by('polygon__distance').first()
    
    # Find nearest dynamic zone
    nearest_dynamic = DynamicZone.objects.filter(
        geometry__distance_lte=(user_point, D(km=radius_km)),
        state__in=['active', 'escalated']
    ).order_by('geometry__distance').first()
    
    # Find nearest reading
    nearest_reading = FloodReading.objects.filter(
        location__distance_lte=(user_point, D(km=radius_km))
    ).order_by('location__distance').first()
    
    return {
        'type': 'coordinates',
        'lat': lat,
        'lon': lon,
        'nearest_zone': {
            'id': nearest_zone.id,
            'name': nearest_zone.name,
            'risk_score': float(nearest_zone.risk_score or 0),
            'distance_m': round(float(nearest_zone.polygon.distance(user_point) * 111320), 1) if nearest_zone else None,
        } if nearest_zone else None,
        'nearest_dynamic_zone': {
            'id': nearest_dynamic.id,
            'name': nearest_dynamic.name,
            'risk_score': float(nearest_dynamic.risk_score or 0),
            'state': nearest_dynamic.state,
        } if nearest_dynamic else None,
        'nearest_reading': {
            'id': nearest_reading.id,
            'water_level': nearest_reading.water_level_metres,
            'risk_score': float(nearest_reading.risk_score or 0),
            'timestamp': nearest_reading.timestamp.isoformat(),
        } if nearest_reading else None,
    }


def _search_by_place_name(query, radius_km):
    """Search by place name using OSM Nominatim."""
    try:
        import requests
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': query,
                'format': 'json',
                'limit': 5,
                'addressdetails': 1,
            },
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        
        if not data:
            return {'type': 'place_name', 'query': query, 'results': []}
        
        results = []
        for item in data[:5]:
            results.append({
                'lat': float(item.get('lat', 0)),
                'lon': float(item.get('lon', 0)),
                'display_name': item.get('display_name', ''),
                'type': item.get('class', 'place'),
                'importance': item.get('importance', 0),
            })
        
        return {
            'type': 'place_name',
            'query': query,
            'results': results,
        }
    except Exception as e:
        logger.warning(f"Place name search failed: {e}")
        return {'type': 'place_name', 'query': query, 'error': str(e)}


def _search_osm_feature(query, radius_km):
    """Search for OSM features (hospital, school, river, etc.)."""
    feature_types = {
        'hospital': 'hospital',
        'school': 'school',
        'police': 'police',
        'fire': 'fire_station',
        'river': 'river',
        'lake': 'water',
        'market': 'marketplace',
        'bridge': 'bridge',
        'road': 'road',
    }
    
    feature_type = None
    for key, osm_type in feature_types.items():
        if key in query.lower():
            feature_type = osm_type
            break
    
    if not feature_type:
        return {'type': 'osm_feature', 'query': query, 'results': []}
    
    try:
        import requests
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': query,
                'format': 'json',
                'limit': 10,
                'featuretype': feature_type,
            },
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        
        results = []
        for item in data[:10]:
            results.append({
                'lat': float(item.get('lat', 0)),
                'lon': float(item.get('lon', 0)),
                'display_name': item.get('display_name', ''),
                'type': item.get('class', 'place'),
            })
        
        return {
            'type': 'osm_feature',
            'query': query,
            'feature_type': feature_type,
            'results': results,
        }
    except Exception as e:
        logger.warning(f"OSM feature search failed: {e}")
        return {'type': 'osm_feature', 'query': query, 'error': str(e)}


def _get_weather_data(lat, lon):
    """Get weather data for coordinates."""
    try:
        from core.data_sources.aggregator import build_risk_feature_vector
        features = build_risk_feature_vector(lat, lon, 'search')
        return {
            'temperature': features.get('temperature'),
            'humidity': features.get('humidity'),
            'rainfall_1h_mm': features.get('rainfall_1h_mm'),
            'precip_intensity': features.get('precip_intensity'),
            'river_discharge': features.get('river_discharge'),
            'wind_speed': features.get('wind_speed'),
            'sources_available': features.get('sources_available', 0),
            'data_confidence': features.get('data_confidence', 'low'),
        }
    except Exception as e:
        logger.warning(f"Weather data fetch failed: {e}")
        return None


def _get_flood_risk(lat, lon):
    """Get flood risk for coordinates."""
    try:
        from core.analytics.scoring import calculate_feature_risk
        from core.data_sources.aggregator import build_risk_feature_vector
        features = build_risk_feature_vector(lat, lon, 'search')
        risk_score = calculate_feature_risk(features)
        return {
            'risk_score': round(float(risk_score), 3),
            'risk_level': _risk_level(risk_score),
            'confidence': features.get('data_confidence', 'low'),
        }
    except Exception as e:
        logger.warning(f"Risk calculation failed: {e}")
        return None


def _get_prediction(lat, lon):
    """Get flood prediction for coordinates."""
    try:
        from core.data_sources.aggregator import build_risk_feature_vector
        features = build_risk_feature_vector(lat, lon, 'search')
        return {
            '24h_risk': features.get('risk_24h'),
            '48h_risk': features.get('risk_48h'),
            '7d_risk': features.get('risk_7d'),
        }
    except Exception:
        return None


def _find_nearby_shelters(lat, lon, radius_km):
    """Find nearby shelters (low-risk zones)."""
    try:
        user_point = Point(lon, lat, srid=4326)
        shelters = AlertZone.objects.filter(
            risk_score__lte=0.4,
            polygon__distance_lte=(user_point, D(km=radius_km))
        ).order_by('polygon__distance')[:5]
        
        return [
            {
                'id': s.id,
                'name': s.name,
                'risk_score': float(s.risk_score or 0),
                'distance_m': round(float(s.polygon.distance(user_point) * 111320), 1),
            }
            for s in shelters
        ]
    except Exception:
        return []


def _find_nearby_hospitals(lat, lon, radius_km):
    """Find nearby hospitals."""
    try:
        import requests
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': 'hospital',
                'format': 'json',
                'lat': lat,
                'lon': lon,
                'viewbox': f"{lon-radius_km/110},{lat-radius_km/110},{lon+radius_km/110},{lat+radius_km/110}",
                'bounded': 1,
                'limit': 5,
            },
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return [
                {
                    'name': item.get('display_name', '').split(',')[0],
                    'lat': float(item.get('lat', 0)),
                    'lon': float(item.get('lon', 0)),
                    'distance_m': _haversine_m(lat, lon, float(item.get('lat', 0)), float(item.get('lon', 0))),
                }
                for item in data[:5]
            ]
    except Exception:
        pass
    return []


def _find_nearby_police(lat, lon, radius_km):
    """Find nearby police stations."""
    try:
        import requests
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': 'police',
                'format': 'json',
                'lat': lat,
                'lon': lon,
                'viewbox': f"{lon-radius_km/110},{lat-radius_km/110},{lon+radius_km/110},{lat+radius_km/110}",
                'bounded': 1,
                'limit': 5,
            },
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return [
                {
                    'name': item.get('display_name', '').split(',')[0],
                    'lat': float(item.get('lat', 0)),
                    'lon': float(item.get('lon', 0)),
                    'distance_m': _haversine_m(lat, lon, float(item.get('lat', 0)), float(item.get('lon', 0))),
                }
                for item in data[:5]
            ]
    except Exception:
        pass
    return []


def _find_nearby_fire_stations(lat, lon, radius_km):
    """Find nearby fire stations."""
    try:
        import requests
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={
                'q': 'fire_station',
                'format': 'json',
                'lat': lat,
                'lon': lon,
                'viewbox': f"{lon-radius_km/110},{lat-radius_km/110},{lon+radius_km/110},{lat+radius_km/110}",
                'bounded': 1,
                'limit': 5,
            },
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return [
                {
                    'name': item.get('display_name', '').split(',')[0],
                    'lat': float(item.get('lat', 0)),
                    'lon': float(item.get('lon', 0)),
                    'distance_m': _haversine_m(lat, lon, float(item.get('lat', 0)), float(item.get('lon', 0))),
                }
                for item in data[:5]
            ]
    except Exception:
        pass
    return []


def _get_safe_routes(lat, lon):
    """Get safe route options from coordinates."""
    try:
        from core.views import _provide_safe_routes
        routes = _provide_safe_routes(lat, lon)
        return routes[:3] if routes else []
    except Exception:
        return []


def _generate_decision_support(lat, lon, search_result):
    """Generate decision support JSON."""
    risk = search_result.get('flood_risk', {}) or {}
    weather = search_result.get('weather', {}) or {}
    pop_exp = search_result.get('population_exposure') or {}
    infra_exp = search_result.get('infrastructure_exposure') or {}
    
    risk_score = risk.get('risk_score', 0) if risk else 0
    
    decision = {
        'current_situation': _assess_situation(risk_score, weather),
        'evidence': _collect_evidence(weather, risk),
        'flood_probability': f"{risk_score * 100:.1f}%",
        'expected_water_depth': _estimate_depth(risk_score),
        'expected_velocity': _estimate_velocity(risk_score),
        'expected_arrival_time': '0-2 hours' if risk_score > 0.7 else '2-6 hours' if risk_score > 0.4 else '>6 hours',
        'expected_duration': '24-48 hours' if risk_score > 0.7 else '6-24 hours' if risk_score > 0.4 else '<6 hours',
        'confidence': risk.get('confidence', 'low') if risk else 'low',
        'risk_drivers': _identify_risk_drivers(weather),
        'affected_population': pop_exp.get('estimated_population', 0),
        'affected_infrastructure': infra_exp,
        'critical_services': _assess_critical_services(search_result),
        'priority': _determine_priority(risk_score),
        'incident_classification': _classify_incident(risk_score, weather),
        'recommended_actions': _recommend_actions(risk_score),
        'resource_allocation': _recommend_resources(risk_score),
        'evacuation_radius': f"{_evacuation_radius(risk_score):.1f} km",
        'shelter_recommendations': (search_result.get('nearby_shelters') or [])[:3],
        'medical_response': 'Activate emergency medical services' if risk_score > 0.7 else 'Standby' if risk_score > 0.4 else 'Routine',
        'police_response': 'Deploy traffic control and evacuation support' if risk_score > 0.7 else 'Standby' if risk_score > 0.4 else 'Routine',
        'fire_response': 'Deploy swift water rescue teams' if risk_score > 0.7 else 'Standby' if risk_score > 0.4 else 'Routine',
        'ngo_response': 'Coordinate with humanitarian partners' if risk_score > 0.5 else 'Monitoring',
        'meteorological_actions': 'Issue flood watch/warning' if risk_score > 0.5 else 'Continue monitoring',
        'county_actions': 'Activate county emergency operations center' if risk_score > 0.7 else 'Alert county disaster committee',
        'national_actions': 'National situation report' if risk_score > 0.85 else 'Continue monitoring',
        'recovery_planning': 'Initiate early recovery planning' if risk_score > 0.5 else 'Standard recovery timeline',
    }
    
    return decision


def _assess_situation(risk_score, weather):
    """Assess current situation."""
    if risk_score > 0.85:
        return "Critical flood conditions. Immediate action required."
    elif risk_score > 0.7:
        return "High flood risk. Prepare for evacuation."
    elif risk_score > 0.4:
        return "Moderate flood risk. Monitor conditions closely."
    elif risk_score > 0.2:
        return "Low flood risk. Standard monitoring."
    return "No immediate flood risk."


def _collect_evidence(weather, risk):
    """Collect evidence for decision support."""
    evidence = []
    if weather:
        if weather.get('rainfall_1h_mm', 0) > 10:
            evidence.append(f"Heavy rainfall: {weather['rainfall_1h_mm']}mm in last hour")
        if weather.get('river_discharge', 0) > 20:
            evidence.append(f"High river discharge: {weather['river_discharge']} m³/s")
        if weather.get('humidity', 0) > 80:
            evidence.append(f"High humidity: {weather['humidity']}%")
    if risk:
        evidence.append(f"Calculated risk score: {risk.get('risk_score', 0)}")
        evidence.append(f"Data confidence: {risk.get('confidence', 'unknown')}")
    return evidence


def _estimate_depth(risk_score):
    """Estimate expected flood depth."""
    if risk_score > 0.85:
        return "1.5-3.0 meters"
    elif risk_score > 0.7:
        return "0.5-1.5 meters"
    elif risk_score > 0.4:
        return "0.2-0.5 meters"
    elif risk_score > 0.2:
        return "0.0-0.2 meters"
    return "No flooding expected"


def _estimate_velocity(risk_score):
    """Estimate flood velocity."""
    if risk_score > 0.85:
        return "2.0-3.5 m/s (fast)"
    elif risk_score > 0.7:
        return "1.0-2.0 m/s (moderate-fast)"
    elif risk_score > 0.4:
        return "0.5-1.0 m/s (moderate)"
    elif risk_score > 0.2:
        return "0.0-0.5 m/s (slow)"
    return "No flow"


def _identify_risk_drivers(weather):
    """Identify primary risk drivers."""
    drivers = []
    if not weather:
        return drivers
    if weather.get('rainfall_1h_mm', 0) > 10:
        drivers.append("Heavy rainfall")
    if weather.get('river_discharge', 0) > 20:
        drivers.append("High river discharge")
    if weather.get('humidity', 0) > 80:
        drivers.append("Saturated ground conditions")
    if weather.get('wind_speed', 0) > 50:
        drivers.append("High winds (storm surge risk)")
    return drivers if drivers else ["No significant risk drivers identified"]


def _assess_critical_services(search_result):
    """Assess critical services status."""
    services = {
        'hospitals_affected': 0,
        'schools_affected': 0,
        'power_affected': False,
        'water_affected': False,
        'transport_disrupted': False,
    }
    # Placeholder for infrastructure analysis
    return services


def _determine_priority(risk_score):
    """Determine incident priority."""
    if risk_score > 0.85:
        return 1  # Critical
    elif risk_score > 0.7:
        return 2  # High
    elif risk_score > 0.4:
        return 3  # Medium
    return 4  # Low


def _classify_incident(risk_score, weather):
    """Classify incident type."""
    if risk_score > 0.85:
        return "Major Flood Event"
    elif risk_score > 0.7:
        return "Flood Warning"
    elif risk_score > 0.4:
        return "Flood Watch"
    elif risk_score > 0.2:
        return "Flood Advisory"
    return "No Incident"


def _recommend_actions(risk_score):
    """Recommend actions based on risk level."""
    if risk_score > 0.85:
        return [
            "IMMEDIATE EVACUATION ordered for all affected areas",
            "Deploy emergency response teams",
            "Activate all emergency services",
            "Establish emergency operations center",
            "Issue public emergency alert via all channels",
        ]
    elif risk_score > 0.7:
        return [
            "Prepare for potential evacuation",
            "Deploy monitoring teams to affected areas",
            "Alert emergency services",
            "Issue public flood warning",
            "Pre-position rescue equipment",
        ]
    elif risk_score > 0.4:
        return [
            "Increase monitoring frequency",
            "Alert local disaster committee",
            "Prepare evacuation routes",
            "Issue public flood watch",
        ]
    elif risk_score > 0.2:
        return [
            "Continue routine monitoring",
            "Review emergency plans",
            "Inform local authorities",
        ]
    return ["No action required"]


def _recommend_resources(risk_score):
    """Recommend resource allocation."""
    if risk_score > 0.85:
        return {
            'personnel': 'All available emergency personnel',
            'vehicles': 'Boats, helicopters, 4x4 vehicles',
            'equipment': 'Swift water rescue, pumps, generators',
            'supplies': 'Food, water, medicine, blankets for 1000+ people',
        }
    elif risk_score > 0.7:
        return {
            'personnel': 'Emergency response teams on standby',
            'vehicles': '4x4 vehicles, boats',
            'equipment': 'Pumps, rescue equipment',
            'supplies': 'Emergency supplies for 500+ people',
        }
    return {'personnel': 'Monitoring team', 'vehicles': 'Standard', 'equipment': 'Basic', 'supplies': 'Minimal'}


def _evacuation_radius(risk_score):
    """Calculate evacuation radius in km."""
    if risk_score > 0.85:
        return 5.0
    elif risk_score > 0.7:
        return 3.0
    elif risk_score > 0.4:
        return 1.5
    return 0.5


def _estimate_population_exposure(lat, lon):
    """Estimate population exposed to flood risk."""
    try:
        user_point = Point(lon, lat, srid=4326)
        admin = AdministrativeBoundary.objects.filter(
            geometry__contains=user_point,
            boundary_type__in=['ward', 'village']
        ).first()
        
        if admin and admin.metadata:
            pop = admin.metadata.get('population', 0)
            return {
                'estimated_population': pop,
                'density': admin.metadata.get('population_density', 0),
                'source': 'administrative_boundary',
            }
        
        # Fallback: estimate from H3 cell
        cell = get_or_create_h3_cell(lat, lon)
        if cell and cell.population_density:
            return {
                'estimated_population': int(cell.population_density * 1.1),
                'density': cell.population_density,
                'source': 'h3_cell_estimate',
            }
        
        return {'estimated_population': 0, 'source': 'no_data'}
    except Exception:
        return {'estimated_population': 0, 'source': 'error'}


def _estimate_infrastructure_exposure(lat, lon):
    """Estimate infrastructure exposure."""
    try:
        user_point = Point(lon, lat, srid=4326)
        
        # Count buildings via OSM (simplified)
        # In production, use Overpass API or pre-loaded building data
        return {
            'buildings_affected': 0,
            'roads_affected_km': 0,
            'hospitals_affected': 0,
            'schools_affected': 0,
            'power_infrastructure': False,
            'water_infrastructure': False,
            'source': 'estimated',
        }
    except Exception:
        return {}


def _get_historical_flooding(lat, lon):
    """Get historical flooding data."""
    try:
        user_point = Point(lon, lat, srid=4326)
        historical = FloodReading.objects.filter(
            location__distance_lte=(user_point, D(km=5)),
            risk_score__gt=0.5
        ).order_by('-timestamp')[:10]
        
        return [
            {
                'id': h.id,
                'timestamp': h.timestamp.isoformat(),
                'risk_score': float(h.risk_score or 0),
                'water_level': h.water_level_metres,
            }
            for h in historical
        ]
    except Exception:
        return []


def _get_administrative_hierarchy(lat, lon):
    """Get administrative hierarchy for coordinates."""
    try:
        user_point = Point(lon, lat, srid=4326)
        boundaries = AdministrativeBoundary.objects.filter(
            geometry__contains=user_point
        ).order_by('boundary_type')
        
        hierarchy = {}
        for b in boundaries:
            hierarchy[b.boundary_type] = {
                'id': b.id,
                'name': b.name,
                'parent': b.parent.name if b.parent else None,
            }
        
        return hierarchy if hierarchy else None
    except Exception:
        return None


def _get_h3_information(lat, lon):
    """Get H3 information for coordinates."""
    try:
        resolution = _get_h3_resolution(lat, lon)
        cell = get_or_create_h3_cell(lat, lon, resolution=resolution)
        if cell:
            return {
                'h3_index': cell.h3_index,
                'resolution': cell.resolution,
                'risk_score': float(cell.current_risk_score or 0),
                'population_density': cell.population_density,
                'historical_flood_frequency': cell.historical_flood_frequency,
            }
    except Exception:
        pass
    return None


def _risk_level(risk_score):
    """Convert risk score to level."""
    if risk_score >= 0.85:
        return 'CRITICAL'
    elif risk_score >= 0.7:
        return 'HIGH'
    elif risk_score >= 0.4:
        return 'MODERATE'
    elif risk_score >= 0.2:
        return 'LOW'
    return 'MINIMAL'


def _haversine_m(lat1, lon1, lat2, lon2):
    """Calculate distance in meters between two coordinates."""
    radius = 6371000
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))
