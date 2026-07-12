"""
H3-based flood risk overlay for safe route planning.

This module converts AlertZone and FloodReading data into H3 cell risk scores
that can be used by the routing engine to avoid flooded roads.
"""

import logging
from django.conf import settings
from django.core.cache import cache
from django.contrib.gis.geos import Point
from core.models import AlertZone, FloodReading

logger = logging.getLogger(__name__)

H3_CACHE_TIMEOUT = 15 * 60  # 15 minutes
H3_RESOLUTION_URBAN = 7     # ~1km² cells for cities
H3_RESOLUTION_RURAL = 5     # ~12km² cells for rural areas


def _get_h3_resolution(lat, lon):
    """
    Choose H3 resolution based on location density.
    Urban areas get finer resolution.
    """
    # Simple heuristic: use finer resolution for known dense areas
    # In production, this could use population density data
    urban_centers = [
        (-1.2921, 36.8219),   # Nairobi
        (39.9042, 116.4074),  # Beijing
        (31.2304, 121.4737),  # Shanghai
        (19.0760, 72.8777),   # Mumbai
    ]
    
    for urban_lat, urban_lon in urban_centers:
        if abs(lat - urban_lat) < 0.5 and abs(lon - urban_lon) < 0.5:
            return H3_RESOLUTION_URBAN
    return H3_RESOLUTION_RURAL


def get_risk_for_h3_cell(h3_index):
    """
    Get flood risk score for an H3 cell.
    Checks cache first, then calculates from AlertZones.
    """
    cache_key = f"h3:{h3_index}:risk_score"
    cached = cache.get(cache_key)
    if cached is not None:
        return float(cached)

    risk = _calculate_h3_risk(h3_index)
    cache.set(cache_key, risk, H3_CACHE_TIMEOUT)
    return risk


def _get_risk_level_label(risk_score):
    """Convert risk score to three-tier label (high, medium, low)."""
    if risk_score >= 0.7:
        return 'high'
    elif risk_score >= 0.4:
        return 'medium'
    return 'low'


def get_h3_cell_for_point(lat, lon, resolution=None):
    """
    Get the H3 cell index for a specific point.
    Returns cell index and risk data.
    """
    try:
        import h3
    except ImportError:
        return None

    if resolution is None:
        resolution = _get_h3_resolution(lat, lon)

    try:
        cell = h3.geo_to_h3(float(lat), float(lon), resolution)
        risk = get_risk_for_h3_cell(cell)
        return {
            'h3_index': cell,
            'lat': lat,
            'lon': lon,
            'risk_score': round(risk, 3),
            'risk_level': _get_risk_level_label(risk),
            'resolution': resolution,
        }
    except Exception as e:
        logger.warning(f"Failed to get H3 cell for point {lat},{lon}: {e}")
        return None


def get_h3_cells_for_bbox(min_lat, min_lon, max_lat, max_lon, resolution=None):
    """
    Get all H3 cells within a bounding box for map visualization.
    Returns list of H3 indices and their risk scores.
    """
    try:
        import h3
    except ImportError:
        return []

    try:
        if resolution is None:
            resolution = H3_RESOLUTION_URBAN

        # Get cells covering the polygon area
        from django.contrib.gis.geos import Polygon
        bbox_polygon = Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat))

        cells = h3.polyfill_geojson(
            {
                "type": "Polygon",
                "coordinates": [[
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]]
            },
            resolution
        )

        cell_data = []
        for cell in cells:
            risk = get_risk_for_h3_cell(cell)
            if risk > 0:
                cell_data.append({
                    'h3_index': cell,
                    'risk_score': round(risk, 3),
                    'risk_level': _get_risk_level_label(risk),
                })

        return cell_data
    except Exception as e:
        logger.warning(f"Failed to get H3 cells for bbox: {e}")
        return []


def _calculate_h3_risk(h3_index):
    """
    Calculate flood risk for an H3 cell by checking intersection with AlertZones.
    """
    try:
        import h3
        # Get the boundary polygon of the H3 cell
        boundary = h3.h3_to_geo_boundary(h3_index, geo_json=True)
        if not boundary or len(boundary) < 3:
            return 0.0
        
        from django.contrib.gis.geos import Polygon
        cell_polygon = Polygon(boundary, srid=4326)
        
        # Find all zones that intersect this cell
        intersecting_zones = AlertZone.objects.filter(polygon__intersects=cell_polygon)
        
        if not intersecting_zones.exists():
            return 0.0
        
        # Average the risk scores of intersecting zones
        total_risk = 0.0
        count = 0
        for zone in intersecting_zones:
            total_risk += float(zone.risk_score or 0)
            count += 1
        
        return total_risk / count if count > 0 else 0.0
    except Exception as e:
        logger.warning(f"Failed to calculate H3 risk for cell {h3_index}: {e}")
        return 0.0


def get_risk_for_route(route_geometry, resolution=None):
    """
    Calculate average flood risk for a route.
    
    Args:
        route_geometry: List of [lon, lat] coordinates
        resolution: H3 resolution (auto-detected if None)
    
    Returns:
        dict with risk metrics
    """
    if not route_geometry or len(route_geometry) < 2:
        return {'avg_risk': 0.0, 'max_risk': 0.0, 'cell_count': 0}
    
    try:
        import h3
    except ImportError:
        return {'avg_risk': 0.0, 'max_risk': 0.0, 'cell_count': 0, 'error': 'h3 not installed'}
    
    # Sample points along the route and get H3 cells
    h3_cells = set()
    for point in route_geometry:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            lon, lat = point[0], point[1]
        elif isinstance(point, dict):
            lat = point.get('lat', point.get('latitude'))
            lon = point.get('lng', point.get('lon', point.get('longitude')))
        else:
            continue
        
        if lat is None or lon is None:
            continue
        
        try:
            lat_f = float(lat)
            lon_f = float(lon)
            if resolution is None:
                resolution = _get_h3_resolution(lat_f, lon_f)
            h3_cell = h3.geo_to_h3(lat_f, lon_f, resolution)
            h3_cells.add(h3_cell)
        except (ValueError, TypeError):
            continue
    
    if not h3_cells:
        return {'avg_risk': 0.0, 'max_risk': 0.0, 'cell_count': 0}
    
    # Get risk for each cell
    risks = [get_risk_for_h3_cell(cell) for cell in h3_cells]
    
    return {
        'avg_risk': round(sum(risks) / len(risks), 3) if risks else 0.0,
        'max_risk': round(max(risks), 3) if risks else 0.0,
        'cell_count': len(h3_cells),
        'resolution': resolution,
    }


def get_risk_label(risk_score):
    """Convert risk score to human-readable label."""
    if risk_score >= 0.85:
        return 'CRITICAL'
    elif risk_score >= 0.7:
        return 'HIGH'
    elif risk_score >= 0.4:
        return 'MODERATE'
    else:
        return 'LOW'


def h3_index_to_geojson(h3_index):
    """Convert H3 index to GeoJSON polygon for map display."""
    try:
        import h3
        boundary = h3.h3_to_geo_boundary(h3_index, geo_json=True)
        if boundary:
            return {
                'type': 'Polygon',
                'coordinates': [boundary + [boundary[0]]]  # Close the ring
            }
    except Exception:
        pass
    return None
