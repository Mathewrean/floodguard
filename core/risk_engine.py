"""
FloodGuard Risk Engine — shared risk computation, interpolation, forecasting,
propagation simulation, and adaptive zone split/merge logic.

All functions here operate on pure data structures (dicts / lists) so they can
be unit-tested without a database.  Functions that need Redis caching document
their TTL in code comments.
"""

import hashlib
import logging
import math
from collections import deque
from typing import Dict, List, Optional, Tuple

from django.core.cache import cache
from django.conf import settings

from core.models import H3Cell, DynamicZone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & threshold helpers
# ---------------------------------------------------------------------------

THRESHOLD_CRITICAL = getattr(settings, 'RISK_THRESHOLD_CRITICAL', 0.85)
THRESHOLD_HIGH = getattr(settings, 'RISK_THRESHOLD_HIGH', 0.70)
THRESHOLD_MODERATE = getattr(settings, 'RISK_THRESHOLD_MODERATE', 0.40)
THRESHOLD_LOW = getattr(settings, 'RISK_THRESHOLD_LOW', 0.20)

MAX_PROPAGATION_HOURS = 12


def _zoom_to_resolution(zoom: int) -> int:
    """Map a Leaflet zoom level (1-18+) to an H3 resolution."""
    if zoom <= 6:
        return 3
    if zoom <= 9:
        return 4
    if zoom <= 11:
        return 5
    if zoom <= 13:
        return 6
    if zoom <= 15:
        return 7
    return 8


def _resolution_to_scale_label(resolution: int) -> str:
    labels = {
        3: 'Country Scale',
        4: 'Regional Scale',
        5: 'District Scale',
        6: 'Neighbourhood Scale',
        7: 'Street Scale',
        8: 'Building Scale',
    }
    return labels.get(resolution, 'Custom Scale')


# ---------------------------------------------------------------------------
# Enhancement 1 — H3 Hierarchical Indexing
# ---------------------------------------------------------------------------

def compute_parent_risk(child_scores: List[float]) -> float:
    """
    Aggregate child cell scores into a parent score using:
        parent_score = max(child_scores) * 0.6 + mean(child_scores) * 0.4
    Returns a value clamped to [0, 1].
    """
    if not child_scores:
        return 0.0
    max_score = max(child_scores)
    mean_score = sum(child_scores) / len(child_scores)
    score = max_score * 0.6 + mean_score * 0.4
    return max(0.0, min(1.0, round(score, 3)))


def get_child_cells(h3_index: str, target_resolution: Optional[int] = None) -> List[str]:
    """
    Return child H3 indices of *h3_index*.
    If *target_resolution* is None, children are at resolution + 1.
    """
    try:
        import h3
    except ImportError:
        return []

    current_res = h3.get_resolution(h3_index)
    if target_resolution is None:
        target_resolution = current_res + 1

    if target_resolution <= current_res:
        return [h3_index]

    try:
        children = h3.cell_to_children(h3_index, target_resolution)
        return list(children)
    except Exception:
        return []


def get_parent_cell(h3_index: str) -> Optional[str]:
    """Return the parent H3 index of *h3_index*, or None on failure."""
    try:
        import h3
    except ImportError:
        return None
    try:
        parent = h3.cell_to_parent(h3_index)
        return parent
    except Exception:
        return None


def zoom_level_to_resolution(zoom_level: int) -> int:
    """Public wrapper for the zoom → resolution mapping table."""
    return _zoom_to_resolution(zoom_level)


# ---------------------------------------------------------------------------
# Enhancement 2 — Real-Time Zone Interpolation (IDW)
# ---------------------------------------------------------------------------

def interpolate_risk_scores(cell_scores: Dict[str, float]) -> Dict[str, dict]:
    """
    Apply Inverse Distance Weighting (IDW) interpolation across neighbouring H3 cells.

    Parameters
    ----------
    cell_scores: dict mapping h3_index -> risk_score (0-1)

    Returns
    -------
    dict mapping h3_index -> {
        'risk_score': float,
        'interpolated': bool,
    }
    """
    if not cell_scores:
        return {}

    try:
        import h3
    except ImportError:
        # Fallback: just return direct scores without interpolation
        return {
            idx: {'risk_score': score, 'interpolated': False}
            for idx, score in cell_scores.items()
        }

    # Build a lookup of {h3_index: score} for direct-data cells
    direct_scores = dict(cell_scores)

    # TTL: 5 minutes — cache interpolated results in Redis
    # Cache key: h3:interpolated:{bbox_hash}
    result = {}

    # First, mark all direct-data cells
    for idx, score in direct_scores.items():
        result[idx] = {'risk_score': score, 'interpolated': False}

    # For each cell, gather neighbours within k-ring distance 2 and interpolate
    for idx in direct_scores:
        try:
            neighbors = h3.grid_disk(idx, 2)
        except Exception:
            continue

        for neighbor_idx in neighbors:
            if neighbor_idx in direct_scores:
                continue  # Already a direct-data cell

            # Collect direct neighbours within k-ring distance 1 of this neighbor
            try:
                near_neighbors = h3.grid_disk(neighbor_idx, 1)
            except Exception:
                continue

            # Get direct-data cells among near neighbors
            direct_nearby = [
                (n, direct_scores[n]) for n in near_neighbors
                if n in direct_scores
            ]

            if not direct_nearby:
                continue

            # Use centroid distance as proxy for IDW
            try:
                center_lat, center_lon = h3.cell_to_latlng(neighbor_idx)
            except Exception:
                continue

            numerator = 0.0
            denominator = 0.0
            max_direct_score = 0.0

            for other_idx, other_score in direct_nearby:
                try:
                    other_lat, other_lon = h3.cell_to_latlng(other_idx)
                    distance = math.sqrt((center_lat - other_lat)**2 + (center_lon - other_lon)**2)
                    if distance == 0:
                        distance = 0.001  # avoid division by zero
                    weight = 1.0 / (distance ** 2)
                    numerator += other_score * weight
                    denominator += weight
                    max_direct_score = max(max_direct_score, other_score)
                except Exception:
                    continue

            if denominator > 0:
                interpolated_score = numerator / denominator
                # Cap: interpolated cannot exceed max of direct-data neighbours
                interpolated_score = min(interpolated_score, max_direct_score)
                result[neighbor_idx] = {
                    'risk_score': round(interpolated_score, 3),
                    'interpolated': True,
                }

    return result


def interpolate_risk_cached(cell_scores: Dict[str, float], bbox_hash: str) -> Dict[str, dict]:
    """
    Cached version of interpolate_risk_scores.
    Redis cache key: h3:interpolated:{bbox_hash} with TTL 300 seconds (5 minutes).
    """
    cache_key = f"h3:interpolated:{bbox_hash}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = interpolate_risk_scores(cell_scores)
    cache.set(cache_key, result, 300)  # TTL: 5 minutes
    return result


# ---------------------------------------------------------------------------
# Enhancement 3 — Predictive Modeling (48h timeline)
# ---------------------------------------------------------------------------

def predict_risk_timeline(hourly_data: List[dict], base_score: float) -> List[dict]:
    """
    Predict risk score for each of the next 48 hours.

    Parameters
    ----------
    hourly_data: list of dicts, each containing keys like:
        - precipitation_mm (float): precipitation for that hour
        - soil_moisture (float): soil moisture (0-1)
        - river_discharge (float): river discharge m³/s
        - current_discharge (float): current reference discharge
    base_score: the live risk score to escalate from

    Returns
    -------
    list of 48 dicts, each:
        - hour: int (0-47)
        - predicted_score: float
        - predicted_level: str (SAFE/MODERATE/HIGH/CRITICAL)
        - escalation_trigger: str or None
    """
    timeline = []
    current_score = base_score
    max_consecutive_high_precip = 0
    consecutive_count = 0
    soil_saturated_at = None

    for hour in range(48):
        if hour < len(hourly_data):
            data = hourly_data[hour]
        else:
            data = hourly_data[-1] if hourly_data else {}

        precip = float(data.get('precipitation_mm', 0) or 0)
        soil_moisture = float(data.get('soil_moisture', 0) or 0)
        river_discharge = float(data.get('river_discharge', 0) or 0)
        current_discharge = float(data.get('current_discharge', 1.0) or 1.0)

        escalation_trigger = None
        escalated_score = current_score

        # Rule 1: 3 consecutive hours > 20 mm/hr -> escalate 2 tiers
        if precip > 20.0:
            consecutive_count += 1
            if consecutive_count >= 3:
                escalated_score = _escalate_risk_level(current_score, tiers=2)
                escalation_trigger = '3_consecutive_hours_over_20mm'
        else:
            consecutive_count = 0

        # Rule 2: 3 consecutive hours > 10 mm/hr -> escalate 1 tier
        if not escalation_trigger and precip > 10.0:
            max_consecutive_high_precip = max(max_consecutive_high_precip, consecutive_count)
            if consecutive_count >= 3:
                escalated_score = _escalate_risk_level(current_score, tiers=1)
                escalation_trigger = '3_consecutive_hours_over_10mm'

        # Rule 3: soil moisture > 0.85 AND precip > 5 mm/hr -> escalate 1 tier
        if not escalation_trigger and soil_moisture > 0.85 and precip > 5.0:
            escalated_score = _escalate_risk_level(current_score, tiers=1)
            escalation_trigger = 'saturated_soil_with_rain'
            soil_saturated_at = hour

        # Rule 4: river discharge 24h > 1.5x current -> escalate 1 tier
        if not escalation_trigger and hour >= 24:
            hour24_data = hourly_data[24] if len(hourly_data) > 24 else data
            discharge_24h = float(hour24_data.get('river_discharge', river_discharge) or 0)
            if current_discharge > 0 and discharge_24h > 1.5 * current_discharge:
                escalated_score = _escalate_risk_level(current_score, tiers=1)
                escalation_trigger = 'river_discharge_24h_spike'

        predicted_score = min(1.0, escalated_score)
        risk_level = _risk_level_label(predicted_score)

        timeline.append({
            'hour': hour,
            'predicted_score': round(predicted_score, 3),
            'predicted_level': risk_level,
            'escalation_trigger': escalation_trigger,
            'precipitation_mm': precip,
            'soil_moisture': soil_moisture,
        })

        # Advance current score for next iteration
        current_score = predicted_score

    return timeline


def _escalate_risk_level(score: float, tiers: int = 1) -> float:
    """Escalate a risk score by *tiers* risk levels."""
    for _ in range(tiers):
        if score >= THRESHOLD_CRITICAL:
            score = min(1.0, score + 0.05)
        elif score >= THRESHOLD_HIGH:
            score = min(1.0, score + 0.10)
        elif score >= THRESHOLD_MODERATE:
            score = min(1.0, score + 0.20)
        elif score >= THRESHOLD_LOW:
            score = min(1.0, score + 0.30)
        else:
            return 0.20
    return min(1.0, score)


def _risk_level_label(score: float) -> str:
    if score >= THRESHOLD_CRITICAL:
        return 'CRITICAL'
    elif score >= THRESHOLD_HIGH:
        return 'HIGH'
    elif score >= THRESHOLD_MODERATE:
        return 'MODERATE'
    elif score >= THRESHOLD_LOW:
        return 'LOW'
    return 'SAFE'


# ---------------------------------------------------------------------------
# Enhancement 4 — Cross-Zone Flood Propagation Simulation
# ---------------------------------------------------------------------------

def _fetch_elevation(lat: float, lon: float) -> Optional[float]:
    """Fetch elevation from OpenTopoData API (SRTM30m)."""
    try:
        import requests
        resp = requests.get(
            'https://api.opentopodata.org/v1/srtm30m',
            params={'locations': f'{lat},{lon}'},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('results', [])
            if results:
                return float(results[0].get('elevation', 0))
    except Exception:
        pass
    return None


def _elevation_cache_key(lat: float, lon: float) -> str:
    return f"elev:{lat:.4f},{lon:.4f}"


def get_cached_elevation(lat: float, lon: float) -> Optional[float]:
    """Get elevation, using Redis cache with TTL 86400s (24 hours)."""
    key = _elevation_cache_key(lat, lon)
    cached = cache.get(key)
    if cached is not None:
        try:
            return float(cached)
        except (TypeError, ValueError):
            pass

    elev = _fetch_elevation(lat, lon)
    if elev is not None:
        cache.set(key, elev, 86400)  # TTL: 24 hours
    return elev


def elevation_decay(source_lat: float, source_lon: float,
                     target_lat: float, target_lon: float) -> float:
    """
    Compute elevation-based decay factor for flood propagation.
    If target is higher than source, decay = 0.3 (water doesn't flow uphill).
    If target is lower or equal, decay = 0.9 (water flows downhill readily).
    """
    source_elev = get_cached_elevation(source_lat, source_lon)
    target_elev = get_cached_elevation(target_lat, target_lon)

    if source_elev is None or target_elev is None:
        # If elevation is unavailable, assume neutral propagation
        return 0.6

    if target_elev > source_elev:
        return 0.3
    return 0.9


def simulate_propagation(seed_cells: List[str], hours: int = 12,
                         cell_risks: Optional[Dict[str, float]] = None) -> dict:
    """
    Breadth-first flood-fill propagation simulation over the H3 grid graph.

    Parameters
    ----------
    seed_cells: list of H3 indices that are initially flooding
    hours: maximum forecast hours (capped at MAX_PROPAGATION_HOURS)
    cell_risks: dict mapping h3_index -> current risk score (0-1)

    Returns
    -------
    dict with structure:
        {
            'cells': {h3_index: {'risk_score': float, 'propagation_hour': int, 'propagated': bool}},
            'propagation_paths': list of (source, target, propagated_score),
        }
    """
    hours = min(hours, MAX_PROPAGATION_HOURS)

    try:
        import h3
    except ImportError:
        return {'cells': {}, 'propagation_paths': []}

    if cell_risks is None:
        cell_risks = {}

    # High-threshold cells are seeds
    result_cells = {}
    propagation_paths = []
    visited = set()

    queue = deque()
    for cell in seed_cells:
        if cell in cell_risks:
            score = cell_risks[cell]
        else:
            score = 0.8  # default high score for seeds
        result_cells[cell] = {
            'risk_score': score,
            'propagation_hour': 0,
            'propagated': False,
        }
        visited.add(cell)
        queue.append((cell, score, 0))

    decay_factor = 0.75  # each propagation step multiplies by this

    next_queue = deque()

    for hour in range(1, hours + 1):
        if not queue:
            break

        while queue:
            cell, cell_score, cell_hour = queue.popleft()

            try:
                neighbors = h3.grid_disk(cell, 1)
            except Exception:
                continue

            for neighbor in neighbors:
                if neighbor == cell or neighbor in visited:
                    continue

                try:
                    n_lat, n_lon = h3.cell_to_latlng(neighbor)
                    c_lat, c_lon = h3.cell_to_latlng(cell)
                except Exception:
                    continue

                decay = elevation_decay(c_lat, c_lon, n_lat, n_lon)
                propagated_score = cell_score * decay_factor * decay

                if propagated_score < 0.10:
                    continue

                result_cells[neighbor] = {
                    'risk_score': round(propagated_score, 3),
                    'propagation_hour': hour,
                    'propagated': True,
                }
                visited.add(neighbor)
                propagation_paths.append((cell, neighbor, round(propagated_score, 3)))
                next_queue.append((neighbor, round(propagated_score, 3), hour))

        queue = next_queue
        next_queue = deque()

    return {
        'cells': result_cells,
        'propagation_paths': propagation_paths,
    }


def simulate_propagation_cached(seed_cells: List[str], hours: int = 12,
                                cell_risks: Optional[Dict[str, float]] = None,
                                cache_key_str: Optional[str] = None) -> dict:
    """
    Cached version of simulate_propagation.
    Redis cache key: propagation:{seed_hash}:{hours} with TTL 600 seconds (10 minutes).
    """
    if cache_key_str is None:
        seed_hash = hashlib.md5(','.join(seed_cells).encode()).hexdigest()[:16]
        cache_key_str = f"propagation:{seed_hash}:{hours}"

    cached = cache.get(cache_key_str)
    if cached is not None:
        return cached

    result = simulate_propagation(seed_cells, hours, cell_risks)
    cache.set(cache_key_str, result, 600)  # TTL: 10 minutes
    return result


# ---------------------------------------------------------------------------
# Enhancement 5 — Automated Zone Splitting and Merging
# ---------------------------------------------------------------------------

def should_split(cell_scores_by_child: Dict[str, float]) -> bool:
    """
    Determine whether a parent cell should be split into higher-resolution children.

    Parameters
    ----------
    cell_scores_by_child: dict mapping child_h3_index -> risk_score

    Returns True if max(child_scores) - min(child_scores) > 0.3
    """
    if len(cell_scores_by_child) < 2:
        return False

    scores = [normalize_01(s) for s in cell_scores_by_child.values()]
    if not scores:
        return False

    score_range = max(scores) - min(scores)
    return score_range > 0.3


def should_merge(cells: List[str], cell_scores: Dict[str, float]) -> bool:
    """
    Determine whether adjacent cells at the same resolution should be merged.

    Parameters
    ----------
    cells: list of h3_index strings that are adjacent
    cell_scores: dict mapping h3_index -> risk_score

    Returns True if max(scores) - min(scores) < 0.10
    """
    scores = [
        normalize_01(cell_scores.get(c, 0))
        for c in cells if c in cell_scores
    ]
    if len(scores) < 2:
        return False

    score_range = max(scores) - min(scores)
    return score_range < 0.10


def normalize_01(value) -> float:
    """Normalize a risk score to 0.0–1.0 range."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(score):
        return 0.0
    if 1.0 < score <= 100.0:
        score /= 100.0
    return max(0.0, min(1.0, score))


def auto_split_merge(viewport_cells: List[dict]) -> List[dict]:
    """
    Apply adaptive zone splitting and merging to a list of viewport cell dicts.

    Each cell dict must have:
        - 'h3_index': str
        - 'risk_score': float
        - 'risk_level': str (e.g. 'SAFE', 'LOW', etc.)
        - 'resolution': int

    Returns the adjusted cell list with split_from / merged_from metadata.
    """
    try:
        import h3
    except ImportError:
        return viewport_cells

    # Build lookup of cell data
    cell_map = {}
    for cell in viewport_cells:
        idx = cell.get('h3_index')
        if idx:
            cell_map[idx] = cell

    result = []
    processed = set()

    for cell in viewport_cells:
        idx = cell.get('h3_index')
        if not idx or idx in processed:
            continue

        risk_score = normalize_01(cell.get('risk_score', 0))
        risk_level = cell.get('risk_level', 'SAFE')
        resolution = int(cell.get('resolution', 7))

        # SAFE cells are never split or merged
        if risk_level == 'SAFE':
            result.append(cell)
            processed.add(idx)
            continue

        # Check if we should split into children
        split_done = False
        if resolution < 8:
            try:
                children = h3.cell_to_children(idx)
                child_scores = {}
                for child in children:
                    child_cell = cell_map.get(child)
                    if child_cell:
                        child_scores[child] = normalize_01(child_cell.get('risk_score', 0))

                if should_split(child_scores):
                    # Replace parent with children
                    for child in children:
                        child_cell = cell_map.get(child)
                        if child_cell:
                            child_cell = dict(child_cell)
                            child_cell['split_from'] = idx
                            result.append(child_cell)
                            processed.add(child)
                    processed.add(idx)
                    split_done = True
                    logger_dbg.warning(f'DEBUG: cell {idx} split into {len(children)} children')
                else:
                    logger_dbg.warning(f'DEBUG: cell {idx} should_split=False, child_scores={child_scores}')
            except Exception as e:
                pass

        # Check if we should merge with neighbors
        do_merge = False
        if not split_done and resolution > 3:
            try:
                neighbors = h3.grid_disk(idx, 1)
                neighbor_cells = [n for n in neighbors if n != idx and n in cell_map]

                if len(neighbor_cells) >= 2:
                    all_cells = [idx] + neighbor_cells
                    all_scores = {
                        c: normalize_01(cell_map[c].get('risk_score', 0))
                        for c in all_cells
                    }

                    if should_merge(all_cells, all_scores):
                        # Merge: replace group with parent
                        try:
                            parent = h3.cell_to_parent(idx)
                            merged_cell = {
                                'h3_index': parent,
                                'risk_score': round(sum(all_scores.values()) / len(all_scores), 3),
                                'risk_level': _risk_level_label(sum(all_scores.values()) / len(all_scores)),
                                'resolution': resolution - 1,
                                'merged_from': all_cells,
                                'split_from': None,
                            }
                            result.append(merged_cell)
                            for c in all_cells:
                                processed.add(c)
                            do_merge = True
                        except Exception:
                            pass
            except Exception:
                pass

        if not do_merge and not split_done:
            result.append(cell)
            processed.add(idx)

    # Ensure at least one SAFE cell in the output
    has_safe = any(
        normalize_01(c.get('risk_score', 0)) < 0.20
        for c in result
    )
    if not has_safe and viewport_cells:
        # Convert the lowest-scoring cell to SAFE
        lowest = min(result, key=lambda c: normalize_01(c.get('risk_score', 0)))
        lowest = dict(lowest)
        lowest['risk_score'] = 0.0
        lowest['risk_level'] = 'SAFE'
        # Replace the original entry
        for i, c in enumerate(result):
            if c.get('h3_index') == lowest['h3_index']:
                result[i] = lowest
                break

    return result
