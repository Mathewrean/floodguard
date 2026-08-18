"""
H3 Intelligence Engine
Handles resolution selection, caching, aggregation, and spatial indexing.
"""
import logging
import math

from django.conf import settings
from django.core.cache import cache

from core.models import H3Cell, H3CellRelationship, AdministrativeBoundary

logger = logging.getLogger(__name__)

H3_CACHE_TIMEOUT = 15 * 60  # 15 minutes


def _cell_centroid(h3_index):
    """Return an H3 cell centre as latitude/longitude, never GeoJSON order."""
    import h3
    lat, lon = h3.cell_to_latlng(h3_index)
    return float(lat), float(lon)
DEFAULT_RESOLUTION = 7


def _get_h3_resolution(lat, lon, population_density=None, road_density=None, building_density=None, terrain_complexity=None, historical_frequency=None):
    """
    Automatically choose H3 resolution based on multiple factors.
    
    Factors (higher values -> finer resolution):
    - population_density: people per km²
    - road_density: km of roads per km²
    - building_density: buildings per km²
    - terrain_complexity: 0-1 (higher = more complex)
    - historical_frequency: number of past floods per year
    
    Resolution guide:
    - Dense city: 9-10 (~0.1-0.3 km²)
    - Town: 8 (~1.3 km²)
    - Village: 7 (~1.1 km²)
    - Remote areas: 5-6 (~12-52 km²)
    - Ocean/desert: 4 (~100 km²)
    """
    if hasattr(settings, 'H3_RESOLUTION') and settings.H3_RESOLUTION:
        return settings.H3_RESOLUTION
    
    score = 0.0
    weights = {
        'population': 0.35,
        'road': 0.25,
        'building': 0.20,
        'terrain': 0.10,
        'history': 0.10,
    }
    
    if population_density is not None:
        if population_density > 5000:
            score += weights['population'] * 1.0
        elif population_density > 1000:
            score += weights['population'] * 0.7
        elif population_density > 100:
            score += weights['population'] * 0.4
        else:
            score += weights['population'] * 0.1
    
    if road_density is not None:
        if road_density > 10:
            score += weights['road'] * 1.0
        elif road_density > 5:
            score += weights['road'] * 0.7
        elif road_density > 1:
            score += weights['road'] * 0.4
        else:
            score += weights['road'] * 0.1
    
    if building_density is not None:
        if building_density > 1000:
            score += weights['building'] * 1.0
        elif building_density > 100:
            score += weights['building'] * 0.7
        elif building_density > 10:
            score += weights['building'] * 0.4
        else:
            score += weights['building'] * 0.1
    
    if terrain_complexity is not None:
        score += weights['terrain'] * min(terrain_complexity, 1.0)
    
    if historical_frequency is not None:
        if historical_frequency > 5:
            score += weights['history'] * 1.0
        elif historical_frequency > 2:
            score += weights['history'] * 0.7
        elif historical_frequency > 0:
            score += weights['history'] * 0.4
        else:
            score += weights['history'] * 0.1
    
    if score >= 0.75:
        return 10
    elif score >= 0.55:
        return 9
    elif score >= 0.40:
        return 8
    elif score >= 0.25:
        return 7
    elif score >= 0.15:
        return 6
    elif score >= 0.05:
        return 5
    return 4


def get_or_create_h3_cell(lat, lon, resolution=None, **kwargs):
    """
    Get or create an H3Cell for the given coordinates.
    Automatically determines resolution if not provided.
    """
    try:
        import h3
    except ImportError:
        return None
    
    if resolution is None:
        resolution = _get_h3_resolution(lat, lon, **kwargs)
    
    try:
        h3_index = h3.latlng_to_cell(float(lat), float(lon), resolution)
    except Exception:
        return None
    
    centroid_lat, centroid_lon = _cell_centroid(h3_index)
    field_names = {
        'historical_frequency': 'historical_flood_frequency',
        'population_density': 'population_density',
        'road_density': 'road_density',
        'building_density': 'building_density',
        'terrain_complexity': 'terrain_complexity',
        'confidence': 'confidence',
    }
    cell, created = H3Cell.objects.get_or_create(
        h3_index=h3_index,
        defaults={
            'resolution': resolution,
            'centroid_lat': centroid_lat,
            'centroid_lon': centroid_lon,
            'population_density': kwargs.get('population_density'),
            'road_density': kwargs.get('road_density'),
            'building_density': kwargs.get('building_density'),
            'terrain_complexity': kwargs.get('terrain_complexity'),
            'historical_flood_frequency': kwargs.get('historical_frequency', 0.0),
            'confidence': kwargs.get('confidence', 0.0),
        }
    )
    
    if not created:
        changed_fields = []
        # Earlier releases persisted placeholder (0, 0) centroids. Repair them
        # lazily as cells are encountered, without a data migration outage.
        if cell.centroid_lat == 0.0 and cell.centroid_lon == 0.0:
            cell.centroid_lat, cell.centroid_lon = centroid_lat, centroid_lon
            changed_fields.append('centroid_lat')
            changed_fields.append('centroid_lon')
        for key, value in kwargs.items():
            field_name = field_names.get(key)
            if field_name and value is not None and getattr(cell, field_name) != value:
                setattr(cell, field_name, value)
                changed_fields.append(field_name)
        if changed_fields:
            cell.save(update_fields=changed_fields + ['last_updated'])
    
    return cell


def get_h3_cells_for_bbox(min_lat, min_lon, max_lat, max_lon, resolution=None):
    """
    Get all H3 cells within a bounding box.
    """
    try:
        import h3
    except ImportError:
        return []
    
    if resolution is None:
        resolution = DEFAULT_RESOLUTION
    
    try:
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
        h3_indices = h3.h3shape_to_cells(shape, resolution)
    except Exception as e:
        logger.warning(f"H3 bbox query failed: {e}")
        return []
    
    cells = []
    for h3_index in h3_indices:
        centroid_lat, centroid_lon = _cell_centroid(h3_index)
        cell, _ = H3Cell.objects.get_or_create(
            h3_index=h3_index,
            defaults={
                'resolution': resolution,
                'centroid_lat': centroid_lat,
                'centroid_lon': centroid_lon,
            }
        )
        cells.append(cell)
    
    return cells


def get_neighboring_cells(cell, k=1, include_self=False):
    """
    Get neighboring H3 cells using H3 grid_disk.
    Falls back to H3CellRelationship database if h3 not available.
    """
    try:
        import h3
        neighbors = h3.grid_disk(cell.h3_index, k)
        if not include_self:
            neighbors = [n for n in neighbors if n != cell.h3_index]
        
        neighbor_cells = []
        for h3_index in neighbors:
            neighbor_lat, neighbor_lon = _cell_centroid(h3_index)
            neighbor, _ = H3Cell.objects.get_or_create(
                h3_index=h3_index,
                defaults={'resolution': cell.resolution, 'centroid_lat': neighbor_lat, 'centroid_lon': neighbor_lon}
            )
            neighbor_cells.append(neighbor)
        return neighbor_cells
    except Exception:
        return list(H3Cell.objects.filter(
            incoming_relationships__source_cell=cell,
            incoming_relationships__relationship_type='neighbor'
        ))


def build_h3_relationships(resolution=None):
    """
    Build parent-child and neighbor relationships for all H3 cells.
    Should be run periodically or when new cells are created.
    """
    if resolution is None:
        resolutions = H3Cell.objects.values_list('resolution', flat=True).distinct()
    else:
        resolutions = [resolution]
    
    total_created = 0
    for res in resolutions:
        cells = H3Cell.objects.filter(resolution=res)
        cell_map = {c.h3_index: c for c in cells}
        
        for cell in cells:
            try:
                import h3
                parent = h3.cell_to_parent(cell.h3_index)
                if parent in cell_map:
                    H3CellRelationship.objects.get_or_create(
                        source_cell=cell_map[parent],
                        target_cell=cell,
                        relationship_type='child',
                        defaults={'distance_km': None}
                    )
                    H3CellRelationship.objects.get_or_create(
                        source_cell=cell,
                        target_cell=cell_map[parent],
                        relationship_type='parent',
                        defaults={'distance_km': None}
                    )
                
                neighbors = h3.grid_disk(cell.h3_index, 1)
                for neighbor_index in neighbors:
                    if neighbor_index == cell.h3_index:
                        continue
                    if neighbor_index in cell_map:
                        H3CellRelationship.objects.get_or_create(
                            source_cell=cell,
                            target_cell=cell_map[neighbor_index],
                            relationship_type='neighbor',
                            defaults={'distance_km': None}
                        )
                
                k_ring = h3.grid_disk(cell.h3_index, 2)
                for ring_index in k_ring:
                    if ring_index == cell.h3_index:
                        continue
                    if ring_index in cell_map:
                        H3CellRelationship.objects.get_or_create(
                            source_cell=cell,
                            target_cell=cell_map[ring_index],
                            relationship_type='k_ring',
                            defaults={'distance_km': None}
                        )
                        total_created += 1
            except Exception as e:
                logger.warning(f"Failed to build relationships for {cell.h3_index}: {e}")
                continue
    
    logger.info(f"Built {total_created} H3 relationships")
    return total_created


def aggregate_to_resolution(cells, target_resolution):
    """
    Aggregate H3 cells to a coarser resolution.
    Returns list of parent H3 indices.
    """
    try:
        import h3
        parent_indices = set()
        for cell in cells:
            parent = h3.cell_to_parent(cell.h3_index, target_resolution)
            parent_indices.add(parent)
        return list(parent_indices)
    except Exception:
        return []


def get_cell_risk(h3_index):
    """
    Get cached risk score for an H3 cell.
    """
    cache_key = f"h3:{h3_index}:risk_score"
    cached = cache.get(cache_key)
    if cached is not None:
        return float(cached)
    
    try:
        cell = H3Cell.objects.get(h3_index=h3_index)
        cache.set(cache_key, cell.current_risk_score, H3_CACHE_TIMEOUT)
        return float(cell.current_risk_score)
    except H3Cell.DoesNotExist:
        return 0.0


def update_cell_risk(h3_index, risk_score, confidence=None):
    """
    Update risk score for an H3 cell and refresh cache.
    """
    try:
        centroid_lat, centroid_lon = _cell_centroid(h3_index)
        import h3
        cell, _ = H3Cell.objects.get_or_create(
            h3_index=h3_index,
            defaults={
                'resolution': h3.get_resolution(h3_index),
                'centroid_lat': centroid_lat,
                'centroid_lon': centroid_lon,
            }
        )
        cell.current_risk_score = float(risk_score)
        if confidence is not None:
            cell.confidence = float(confidence)
        cell.save(update_fields=['current_risk_score', 'confidence', 'last_updated'])
        
        cache_key = f"h3:{h3_index}:risk_score"
        cache.set(cache_key, float(risk_score), H3_CACHE_TIMEOUT)
        return cell
    except Exception as e:
        logger.warning(f"Failed to update H3 cell risk for {h3_index}: {e}")
        return None


def get_h3_cell_stats(h3_index):
    """
    Get comprehensive statistics for an H3 cell.
    """
    try:
        import h3
        resolution = h3.get_resolution(h3_index)
        neighbors = get_neighboring_cells(H3Cell.objects.get(h3_index=h3_index), k=2)
        return {
            'h3_index': h3_index,
            'resolution': resolution,
            'neighbors': [n.h3_index for n in neighbors],
            'risk_score': get_cell_risk(h3_index),
        }
    except Exception:
        return None
