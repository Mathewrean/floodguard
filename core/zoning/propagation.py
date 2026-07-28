"""
Hydrological Flood Propagation Engine
Uses DEM analysis, flow direction, flow accumulation, and terrain depression detection
to model realistic flood spread.
"""
import logging
import math
from datetime import timedelta

from django.utils import timezone
from django.contrib.gis.geos import Point, Polygon, MultiPoint
from django.contrib.gis.db.models import Union

from core.models import DynamicZone, H3Cell, FloodPropagation
from core.zoning.h3_intelligence import get_neighboring_cells, get_cell_risk, update_cell_risk

logger = logging.getLogger(__name__)

# Hydrology constants
MANNING_N = 0.035  # Manning's roughness coefficient (typical for urban/floodplain)
CRITICAL_DEPTH_THRESHOLD = 0.3  # meters
FLOOD_VELOCITY_FACTOR = 3.5  # m/s sqrt(g*h)
DEM_FETCH_TIMEOUT = 8  # seconds


# ============================================================
# Digital Elevation Model (DEM) Analysis
# ============================================================

def fetch_elevation_tile(lat, lon):
    """
    Fetch elevation from free DEM sources.
    Tries Open-Meteo Elevation API first, then SRTM via OpenTopography.
    Returns elevation in meters or None.
    """
    try:
        import requests
        url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
        resp = requests.get(url, timeout=DEM_FETCH_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            elevation = data.get('elevation')
            if elevation is not None:
                return float(elevation)
    except Exception:
        pass

    try:
        import requests
        url = (
            f"https://portal.opentopography.org/API/globaldem"
            f"?demtype=SRTMGL3"
            f"&south={lat-0.01}&north={lat+0.01}"
            f"&west={lon-0.01}&east={lon+0.01}"
            f"&outputFormat=JSON"
        )
        resp = requests.get(url, timeout=DEM_FETCH_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return float(data.get('elevation', 0))
    except Exception:
        pass

    return None


def fetch_dem_tile_batch(bbox, resolution_m=30):
    """
    Fetch a DEM tile for a bounding box.
    Returns a dict mapping (lat, lon) -> elevation or None.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    try:
        import requests
        url = (
            f"https://portal.opentopography.org/API/globaldem"
            f"?demtype=SRTMGL3"
            f"&south={min_lat}&north={max_lat}"
            f"&west={min_lon}&east={max_lon}"
            f"&outputFormat=JSON"
        )
        resp = requests.get(url, timeout=DEM_FETCH_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if 'data' in data and data['data']:
                grid = {}
                rows = data['data'].get('rows', [])
                for i, row in enumerate(rows):
                    lat = min_lat + (i / max(1, len(rows) - 1)) * (max_lat - min_lat)
                    for j, val in enumerate(row):
                        lon = min_lon + (j / max(1, len(row) - 1)) * (max_lon - min_lon)
                        if val is not None:
                            grid[(round(lat, 5), round(lon, 5))] = float(val)
                return grid
    except Exception:
        pass

    # Fallback: single-point Open-Meteo for center
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    elev = fetch_elevation_tile(center_lat, center_lon)
    if elev is not None:
        return {(round(center_lat, 5), round(center_lon, 5)): elev}
    return {}


def calculate_terrain_slope(elevations, cell_size_m=30):
    """
    Calculate slope from elevation grid using Horn's method.
    Returns slope in radians and aspect in radians.
    """
    if not elevations or len(elevations) < 9:
        return 0.0, 0.0

    # Extract 3x3 neighborhood (center + 8 neighbors)
    # Assumes elevations is dict with integer keys 0-8 for 3x3 grid
    z = [elevations.get(i, 0) for i in range(9)]
    if z[4] is None:
        return 0.0, 0.0

    dz_dx = ((z[2] + 2*z[5] + z[8]) - (z[0] + 2*z[3] + z[6])) / (8 * cell_size_m)
    dz_dy = ((z[6] + 2*z[7] + z[8]) - (z[0] + 2*z[1] + z[2])) / (8 * cell_size_m)

    slope = math.atan(math.sqrt(dz_dx**2 + dz_dy**2))
    aspect = math.atan2(dz_dy, -dz_dx) if dz_dx != 0 or dz_dy != 0 else 0.0

    return slope, aspect


def calculate_flow_direction(elevations, cell_size_m=30):
    """
    D8 flow direction algorithm.
    Returns direction index 0-7 (E, SE, S, SW, W, NW, N, NE) or -1 for flat/pit.
    """
    if not elevations or len(elevations) < 9:
        return -1

    center = elevations.get(4, 0)
    if center is None:
        return -1

    # Neighbor offsets: [row_delta, col_delta, direction]
    neighbors = [
        (-1, 0, 0),   # N
        (-1, 1, 1),   # NE
        (0, 1, 2),    # E
        (1, 1, 3),    # SE
        (1, 0, 4),    # S
        (1, -1, 5),   # SW
        (0, -1, 6),   # W
        (-1, -1, 7),  # NW
    ]

    max_drop = 0
    direction = -1

    for row_delta, col_delta, dir_idx in neighbors:
        neighbor_idx = 4 + row_delta * 3 + col_delta
        if neighbor_idx < 0 or neighbor_idx > 8:
            continue
        neighbor_elev = elevations.get(neighbor_idx, center)
        if neighbor_elev is None:
            continue
        drop = center - neighbor_elev
        if drop > max_drop:
            max_drop = drop
            direction = dir_idx

    return direction if max_drop > 0 else -1


def calculate_flow_accumulation(dem_grid, cell_size_m=30):
    """
    Calculate flow accumulation using D8 algorithm.
    dem_grid: dict mapping (lat, lon) -> elevation
    Returns dict mapping (lat, lon) -> accumulated cells
    """
    if not dem_grid:
        return {}

    # Build flow direction map
    coords = sorted(dem_grid.keys())
    n = len(coords)
    if n == 0:
        return {}

    # Calculate flow direction for each cell
    flow_dir = {}
    for idx, coord in enumerate(coords):
        lat, lon = coord
        center_elev = dem_grid[coord]

        # Find neighbors in 8 directions
        neighbors = []
        for di in [-1, 0, 1]:
            for dj in [-1, 0, 1]:
                if di == 0 and dj == 0:
                    continue
                neighbor_lat = lat + di * 0.001
                neighbor_lon = lon + dj * 0.001
                neighbor_coord = (round(neighbor_lat, 5), round(neighbor_lon, 5))
                if neighbor_coord in dem_grid:
                    drop = center_elev - dem_grid[neighbor_coord]
                    if drop > 0:
                        neighbors.append((drop, neighbor_coord))

        if neighbors:
            max_drop, max_neighbor = max(neighbors, key=lambda x: x[0])
            flow_dir[coord] = max_neighbor
        else:
            flow_dir[coord] = None

    # Calculate accumulation (reverse flow tracing)
    accumulation = {c: 1 for c in coords}

    # Build reverse map (which cells flow into this cell)
    reverse_map = {}
    for src, dst in flow_dir.items():
        if dst is not None:
            reverse_map.setdefault(dst, []).append(src)

    # Process cells in order of decreasing elevation
    sorted_coords = sorted(coords, key=lambda c: dem_grid[c], reverse=True)
    for coord in sorted_coords:
        for upstream in reverse_map.get(coord, []):
            accumulation[coord] += accumulation[upstream]

    return accumulation


def detect_terrain_depressions(dem_grid, cell_size_m=30):
    """
    Detect terrain depressions (sinks) where water accumulates.
    Returns list of depression centers with depths.
    """
    if not dem_grid:
        return []

    coords = sorted(dem_grid.keys())
    depressions = []

    for idx, coord in enumerate(coords):
        lat, lon = coord
        center_elev = dem_grid[coord]
        is_depression = True
        max_surround = center_elev

        for di in [-1, 0, 1]:
            for dj in [-1, 0, 1]:
                if di == 0 and dj == 0:
                    continue
                neighbor_lat = lat + di * 0.001
                neighbor_lon = lon + dj * 0.001
                neighbor_coord = (round(neighbor_lat, 5), round(neighbor_lon, 5))
                if neighbor_coord in dem_grid:
                    neighbor_elev = dem_grid[neighbor_coord]
                    if neighbor_elev < center_elev:
                        is_depression = False
                        break
                    max_surround = max(max_surround, neighbor_elev)
            if not is_depression:
                break

        if is_depression and max_surround > center_elev:
            depressions.append({
                'center': coord,
                'depth': max_surround - center_elev,
                'elevation': center_elev,
            })

    return depressions


def delineate_watershed(zone, dem_grid=None):
    """
    Delineate watershed boundary for a flood zone.
    Returns watershed polygon geometry or None.
    """
    if dem_grid is None:
        bbox = _get_zone_bbox(zone)
        dem_grid = fetch_dem_tile_batch(bbox)

    if not dem_grid:
        return None

    center_lat = zone.geometry.centroid.y
    center_lon = zone.geometry.centroid.x

    # Find flow accumulation at center
    accumulation = calculate_flow_accumulation(dem_grid)
    center_coord = (round(center_lat, 5), round(center_lon, 5))
    if center_coord not in accumulation:
        return None

    # Trace upstream cells
    upstream_cells = []
    threshold = max(10, accumulation[center_coord] * 0.1)

    for coord, acc in accumulation.items():
        if acc >= threshold:
            upstream_cells.append(coord)

    if not upstream_cells:
        return zone.geometry

    try:
        lats = [c[0] for c in upstream_cells]
        lons = [c[1] for c in upstream_cells]
        mp = MultiPoint([(lon, lat) for lat, lon in zip(lats, lons)], srid=4326)
        watershed = mp.convex_hull.buffer(0.005)
        return watershed
    except Exception:
        return zone.geometry


# ============================================================
# Flood Parameter Estimation
# ============================================================

def estimate_flood_depth(zone, upstream_volume_m3=None, cell_area_m2=900):
    """
    Estimate flood depth based on water volume and terrain.
    Returns depth in meters.
    """
    if upstream_volume_m3 is None:
        upstream_volume_m3 = _estimate_upstream_volume(zone)

    if cell_area_m2 <= 0:
        return 0.0

    depth = upstream_volume_m3 / cell_area_m2
    return min(depth, 10.0)  # Cap at 10m


def estimate_flood_velocity(depth_m, slope_rad=0.01):
    """
    Estimate flood velocity using Manning's equation.
    Returns velocity in m/s.
    """
    if depth_m <= 0:
        return 0.0
    if slope_rad <= 0:
        slope_rad = 0.001

    # Manning's: V = (1/n) * R^(2/3) * S^(1/2)
    # Approximate hydraulic radius R ~ depth for wide floodplains
    hydraulic_radius = depth_m
    velocity = (1.0 / MANNING_N) * (hydraulic_radius ** (2.0 / 3.0)) * (slope_rad ** 0.5)
    return min(velocity, 8.0)  # Cap at 8 m/s


def estimate_flood_arrival_time(distance_m, velocity_ms, slope_factor=1.0):
    """
    Estimate time for flood to reach a downstream cell.
    Returns hours.
    """
    if velocity_ms <= 0:
        return float('inf')
    return (distance_m / velocity_ms) / 3600.0 * slope_factor


def estimate_flood_duration(depth_m, inflow_rate_m3s, area_m2):
    """
    Estimate flood duration based on inflow and storage.
    Returns hours.
    """
    if area_m2 <= 0 or inflow_rate_m3s <= 0:
        return 0.0
    storage_capacity = area_m2 * 2.0  # Assume 2m max depth
    duration_hours = storage_capacity / (inflow_rate_m3s * 3600)
    return min(duration_hours, 168.0)  # Cap at 7 days


def _estimate_upstream_volume(zone):
    """
    Estimate upstream water volume from precipitation and catchment area.
    """
    try:
        from core.data_sources.aggregator import build_risk_feature_vector
        features = build_risk_feature_vector(zone.geometry.centroid.y, zone.geometry.centroid.x, zone.name)
        precip = features.get('rainfall_1h_mm', 0) or 0
        discharge = features.get('river_discharge', 0) or 0

        catchment_area_m2 = zone.geometry.area * 1e10 if zone.geometry.area else 1e6
        precip_volume_m3 = (precip / 1000.0) * catchment_area_m2
        baseflow_volume_m3 = discharge * 3600

        return precip_volume_m3 + baseflow_volume_m3
    except Exception:
        return 1000.0


def _get_zone_bbox(zone):
    if zone.geometry:
        minx, miny, maxx, maxy = zone.geometry.extent
        return (miny, minx, maxy, maxx)
    return (-1.3, 36.8, -1.2, 36.9)


# ============================================================
# River Overflow Simulation
# ============================================================

def simulate_river_overflow(zone, discharge_m3s, bankfull_capacity_m3s=50):
    """
    Simulate river overflow when discharge exceeds bankfull capacity.
    Returns expanded zone geometry and flood parameters.
    """
    if discharge_m3s <= bankfull_capacity_m3s:
        return zone, {'overflow': False, 'depth': 0.0, 'velocity': 0.0}

    overflow_volume = discharge_m3s - bankfull_capacity_m3s
    overflow_fraction = overflow_volume / max(discharge_m3s, 1.0)

    # Expand zone based on overflow
    try:
        expanded_geom = zone.geometry.buffer(overflow_fraction * 0.02)
    except Exception:
        expanded_geom = zone.geometry

    slope, _ = _get_zone_slope(zone)
    depth = estimate_flood_depth(zone, upstream_volume_m3=overflow_volume * 3600)
    velocity = estimate_flood_velocity(depth, slope)

    return zone, {
        'overflow': True,
        'overflow_volume_m3s': overflow_volume,
        'depth_m': round(depth, 2),
        'velocity_ms': round(velocity, 2),
        'expanded_geometry': expanded_geom,
    }


def _get_zone_slope(zone):
    bbox = _get_zone_bbox(zone)
    dem_grid = fetch_dem_tile_batch(bbox)
    if dem_grid:
        center_lat = zone.geometry.centroid.y
        center_lon = zone.geometry.centroid.x
        center_coord = (round(center_lat, 5), round(center_lon, 5))
        if center_coord in dem_grid:
            neighbors = {}
            idx = 0
            for di in range(-1, 2):
                for dj in range(-1, 2):
                    neighbor_coord = (round(center_lat + di * 0.001, 5), round(center_lon + dj * 0.001, 5))
                    if neighbor_coord in dem_grid:
                        neighbors[idx] = dem_grid[neighbor_coord]
                    idx += 1
            return calculate_terrain_slope(neighbors)
    return 0.01, 0.0


# ============================================================
# Enhanced Flood Propagation with Hydrology
# ============================================================

def propagate_flood(zone, forecast_hours=24):
    """
    Predict flood spread using hydrological modeling.
    """
    propagation, _ = FloodPropagation.objects.get_or_create(
        zone=zone,
        forecast_hours=forecast_hours,
        defaults={
            'predicted_risk_score': zone.risk_score,
            'confidence': zone.confidence * 0.8,
        }
    )

    try:
        center_cell = zone.h3_cells.first()
        if not center_cell:
            return propagation

        # Get DEM-based terrain analysis
        bbox = _get_zone_bbox(zone)
        dem_grid = fetch_dem_tile_batch(bbox)
        slope_rad = 0.01
        flow_direction = -1

        if dem_grid:
            center_lat = zone.geometry.centroid.y
            center_lon = zone.geometry.centroid.x
            center_coord = (round(center_lat, 5), round(center_lon, 5))
            if center_coord in dem_grid:
                neighbors = {}
                idx = 0
                for di in range(-1, 2):
                    for dj in range(-1, 2):
                        neighbor_coord = (round(center_lat + di * 0.001, 5), round(center_lon + dj * 0.001, 5))
                        if neighbor_coord in dem_grid:
                            neighbors[idx] = dem_grid[neighbor_coord]
                        idx += 1
                slope_rad, _ = calculate_terrain_slope(neighbors)
                flow_direction = calculate_flow_direction(neighbors)

        # Get H3 neighbors
        neighbors = get_neighboring_cells(center_cell, k=3)
        predicted_cells = []

        # Direction mapping: N=0, NE=1, E=2, SE=3, S=4, SW=5, W=6, NW=7
        direction_vectors = {
            0: (0, 1), 1: (1, 1), 2: (1, 0), 3: (1, -1),
            4: (0, -1), 5: (-1, -1), 6: (-1, 0), 7: (-1, 1)
        }

        for neighbor in neighbors:
            # Base risk decay with distance
            distance_factor = 1.0 - (0.03 * forecast_hours / 24.0)

            # Hydrological factors
            slope_factor = max(0.0, min(1.0, slope_rad * 10))
            velocity = estimate_flood_velocity(zone.risk_score * 2.0, slope_rad)
            arrival_hours = estimate_flood_arrival_time(500, velocity)

            # Flow direction bonus
            direction_bonus = 0.0
            if flow_direction in direction_vectors:
                dl, dk = direction_vectors[flow_direction]
                neighbor_dl = neighbor.centroid_lon - center_cell.centroid_lon
                neighbor_dk = neighbor.centroid_lat - center_cell.centroid_lat
                alignment = (dl * neighbor_dl + dk * neighbor_dk) / max(0.001, math.sqrt(dl**2 + dk**2))
                direction_bonus = max(0.0, min(0.3, alignment * 0.3))

            # Combined risk
            predicted_risk = max(0.0, min(1.0,
                zone.risk_score * distance_factor * (1.0 - slope_factor * 0.2) + direction_bonus
            ))

            update_cell_risk(neighbor.h3_index, predicted_risk, zone.confidence * 0.8)
            predicted_cells.append(neighbor)

        propagation.predicted_cells.set(predicted_cells)
        propagation.predicted_risk_score = max(0.0, zone.risk_score * 0.85)
        propagation.confidence = zone.confidence * 0.8
        propagation.spread_direction = f"Flow-based ({len(predicted_cells)} cells)"
        propagation.estimated_arrival = timezone.now() + timedelta(hours=forecast_hours)
        propagation.save()

        return propagation
    except Exception as e:
        logger.error(f"Flood propagation failed for zone {zone.id}: {e}")
        return propagation


def propagate_for_active_zones(forecast_hours_list=[1, 3, 6, 12, 24, 48]):
    """
    Run propagation for all active zones.
    """
    active_zones = DynamicZone.objects.filter(state__in=['active', 'escalated'])
    total = 0
    for zone in active_zones:
        for hours in forecast_hours_list:
            try:
                propagate_flood(zone, hours)
                total += 1
            except Exception as e:
                logger.warning(f"Propagation failed for zone {zone.id} +{hours}h: {e}")
    logger.info(f"Generated {total} flood propagation predictions")
    return total


def get_propagation_for_zone(zone_id, forecast_hours=24):
    """
    Get propagation prediction for a specific zone.
    """
    try:
        zone = DynamicZone.objects.get(id=zone_id)
        propagation = FloodPropagation.objects.filter(zone=zone, forecast_hours=forecast_hours).first()
        if not propagation:
            propagation = propagate_flood(zone, forecast_hours)

        return {
            'zone_id': zone.id,
            'zone_name': zone.name,
            'forecast_hours': forecast_hours,
            'predicted_risk_score': float(propagation.predicted_risk_score),
            'confidence': float(propagation.confidence),
            'spread_direction': propagation.spread_direction,
            'estimated_arrival': propagation.estimated_arrival.isoformat() if propagation.estimated_arrival else None,
            'predicted_cells': [c.h3_index for c in propagation.predicted_cells.all()],
        }
    except DynamicZone.DoesNotExist:
        return None
    except Exception as e:
        logger.error(f"Failed to get propagation for zone {zone_id}: {e}")
        return None
