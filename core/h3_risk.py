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
    Uses configured bounds or population density heuristics.
    """
    # Check if configured resolution overrides heuristic
    if hasattr(settings, 'H3_RESOLUTION') and settings.H3_RESOLUTION:
        return settings.H3_RESOLUTION
    
    # Simple heuristic: use finer resolution for known dense areas
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
        cell = h3.latlng_to_cell(float(lat), float(lon), resolution)
        risk, cell_data = _get_h3_cell_data(cell, resolution)
        return {
            'h3_index': cell,
            'lat': lat,
            'lon': lon,
            'risk_score': round(risk, 3),
            'risk_level': _get_risk_level_label(risk),
            'resolution': resolution,
            **cell_data,
        }
    except Exception as e:
        logger.warning(f"Failed to get H3 cell for point {lat},{lon}: {e}")
        return None


def _get_h3_cell_data(h3_index, resolution):
    """
    Get enriched H3 cell data including risk and metadata.
    Returns (risk_score, additional_data_dict).
    """
    try:
        import h3
        risk = get_risk_for_h3_cell(h3_index)
        
        # Get GeoJSON boundary
        geo = h3.cells_to_geo([h3_index])
        if not geo or 'coordinates' not in geo:
            return risk, {'boundary': None}
        
        # Find intersecting zones for additional data (without polygon for JSON)
        coords = geo['coordinates'][0]
        if len(coords) < 3:
            return risk, {'boundary': None}
        
        coords_closed = list(coords) + [coords[0]]
        from django.contrib.gis.geos import Polygon
        cell_polygon = Polygon(coords_closed, srid=4326)
        
        # Only get serializable fields
        zones = AlertZone.objects.filter(polygon__intersects=cell_polygon).values(
            'name', 'risk_score'
        )[:5]
        
        return risk, {
            'boundary': geo,
            'intersecting_zones': list(zones),
        }
    except Exception as e:
        logger.warning(f"Failed to get H3 cell data for {h3_index}: {e}")
        return 0.0, {}


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

        # Get cells covering the polygon area using h3 API
        geojson = {
            'type': 'Polygon',
            'coordinates': [[
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]]
        }
        shape = h3.geo_to_h3shape(geojson)
        cells = h3.h3shape_to_cells(shape, resolution)

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
        # Get the boundary polygon of the H3 cell using cells_to_geo
        geo = h3.cells_to_geo([h3_index])
        if not geo or 'coordinates' not in geo:
            return 0.0
        
        # Extract coordinates from the GeoJSON
        # cells_to_geo returns {'type': 'Polygon', 'coordinates': ((...),)}
        coords = geo['coordinates'][0]
        if len(coords) < 3:
            return 0.0
        
        # Close the ring for Django Polygon
        coords = list(coords) + [coords[0]]
        
        from django.contrib.gis.geos import Polygon
        cell_polygon = Polygon(coords, srid=4326)
        
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
        route_geometry: List of [lon, lat] coordinates or dicts
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
            h3_cell = h3.latlng_to_cell(lat_f, lon_f, resolution)
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
        geo = h3.cells_to_geo([h3_index])
        if geo and 'coordinates' in geo:
            return geo
    except Exception:
        pass
    return None


def get_neighboring_cells(h3_index, k=1):
    """
    Get neighboring H3 cells for flood propagation analysis.
    Returns cells within k-ring of the given cell.
    """
    try:
        import h3
        neighbors = h3.grid_disk(h3_index, k)
        return [n for n in neighbors if n != h3_index]
    except Exception as e:
        logger.warning(f"Failed to get neighboring cells for {h3_index}: {e}")
        return []


def get_flood_propagation_cells(h3_index, max_distance_km=5):
    """
    Get cells that could be affected by flood from a source cell.
    Uses H3 grid distance for propagation modeling.
    """
    try:
        import h3
        # Use k-ring approximation (each cell is ~1-12km depending on resolution)
        k = max(1, int(max_distance_km / 1.5))  # Rough approximation
        return get_neighboring_cells(h3_index, k)
    except Exception as e:
        logger.warning(f"Failed flood propagation for {h3_index}: {e}")
        return []


def get_h3_cell_stats(h3_index, resolution=None):
    """
    Get comprehensive statistics for an H3 cell.
    Includes risk, neighboring cells, and flood propagation data.
    """
    try:
        import h3
    except ImportError:
        return None
    
    if resolution is None:
        # Infer resolution from cell
        resolution = h3.get_resolution(h3_index)
    
    # Get base cell data
    cell_data = {
        'h3_index': h3_index,
        'resolution': resolution,
        'neighbors': get_neighboring_cells(h3_index, k=2),
        'risk_score': get_risk_for_h3_cell(h3_index),
        'risk_level': _get_risk_level_label(get_risk_for_h3_cell(h3_index)),
    }
    
    # Get boundary
    geo = h3.cells_to_geo([h3_index])
    if geo and 'coordinates' in geo:
        cell_data['boundary'] = geo
    
    return cell_data
