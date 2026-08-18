"""
Dynamic Zoning Engine
Automatically creates, updates, merges, splits, and retires flood zones.
"""
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos import Polygon, Point, MultiPolygon
from django.contrib.gis.db.models import Union
from django.utils import timezone
from django.db import transaction

from core.models import DynamicZone, H3Cell, FloodReading, IncidentReport, AlertZone, AdministrativeBoundary
from core.data_sources.aggregator import build_risk_feature_vector
from core.analytics.scoring import calculate_feature_risk
from core.zoning.h3_intelligence import get_or_create_h3_cell, get_neighboring_cells, get_cell_risk, update_cell_risk
from core.zoning.lifecycle import transition_zone_state, ZONE_STATES

logger = logging.getLogger(__name__)

DYNAMIC_ZONE_RADIUS_BASE = 300.0
DYNAMIC_ZONE_RADIUS_MAX = 1200.0
HIGH_RISK_THRESHOLD = 0.7
MEDIUM_RISK_THRESHOLD = 0.4
MIN_REPORTS_FOR_ZONE = 3
REPORT_CLUSTER_RADIUS_M = 200


def _latlon_delta(radius_m, lat):
    lat_delta = radius_m / 111320.0
    lon_scale = max(0.2, math.cos(math.radians(lat)))
    lon_delta = radius_m / (111320.0 * lon_scale)
    return lat_delta, lon_delta


def _polygon_from_point(lat, lon, accuracy=None):
    radius_m = max(DYNAMIC_ZONE_RADIUS_BASE, min(DYNAMIC_ZONE_RADIUS_MAX, (accuracy or DYNAMIC_ZONE_RADIUS_BASE) * 2))
    lat_delta, lon_delta = _latlon_delta(radius_m, lat)
    return Polygon.from_bbox((lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta))


def _risk_for_point(lat, lon, zone_name=''):
    try:
        features = build_risk_feature_vector(lat, lon, zone_name)
        risk = calculate_feature_risk(features)
        confidence = 0.5
        sources = features.get('sources_available', 0) or 0
        if sources >= 3:
            confidence = 0.9
        elif sources >= 2:
            confidence = 0.75
        elif sources >= 1:
            confidence = 0.6
        return risk, confidence, features
    except Exception as exc:
        logger.warning("Dynamic zoning risk assessment failed: %s", exc)
        return 0.05, 0.2, {}


def _generate_zone_name(lat, lon, source='dynamic'):
    try:
        import requests as req
        geo = req.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'lat': lat, 'lon': lon, 'format': 'json'},
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=5,
        )
        geo.raise_for_status()
        address = geo.json().get('address', {})
        area = address.get('suburb') or address.get('neighbourhood') or address.get('city_district') or address.get('town') or address.get('city')
        if area:
            return f"Dynamic Zone - {area} ({source})"
    except Exception:
        pass
    return f"Dynamic Zone {lat:.3f},{lon:.3f} ({source})"


def _h3_cells_for_polygon(polygon, resolution):
    try:
        import h3
        coords = list(polygon.coords[0]) if hasattr(polygon, 'coords') and polygon.coords else []
        if not coords:
            return []
        geojson = {'type': 'Polygon', 'coordinates': [coords]}
        h3shape = h3.geo_to_h3shape(geojson)
        indices = h3.h3shape_to_cells(h3shape, resolution)
        return list(indices)
    except Exception as e:
        logger.warning(f"Failed to get H3 cells for polygon: {e}")
        return []


def _h3_cell_from_index(h3_index, resolution=7):
    """Persist the exact H3 cell represented by an index, not a zone centroid."""
    try:
        import h3
        lat, lon = h3.cell_to_latlng(h3_index)
        return get_or_create_h3_cell(lat, lon, resolution=resolution)
    except (ImportError, ValueError):
        return None


# ============================================================
# Trigger 1: Weather Update
# ============================================================

def generate_zone_from_weather(lat, lon, zone_name=None, accuracy=None):
    """
    Generate or update a dynamic zone based on weather data.
    """
    if zone_name is None:
        zone_name = _generate_zone_name(lat, lon, 'weather')
    
    risk, confidence, features = _risk_for_point(lat, lon, zone_name)
    polygon = _polygon_from_point(lat, lon, accuracy)
    h3_indices = _h3_cells_for_polygon(polygon, 7)
    
    zone, created = DynamicZone.objects.get_or_create(
        name=zone_name,
        creation_source='weather',
        defaults={
            'state': 'new',
            'geometry': polygon,
            'risk_score': risk,
            'confidence': confidence,
            'cause': _build_cause_text(features),
            'evidence': features,
            'expires_at': timezone.now() + timedelta(hours=6),
        }
    )
    
    if not created:
        zone.risk_score = risk
        zone.confidence = confidence
        zone.geometry = polygon
        zone.cause = _build_cause_text(features)
        zone.evidence = features
        zone.expires_at = timezone.now() + timedelta(hours=6)
        zone.save()
    
    for h3_index in h3_indices:
        cell = _h3_cell_from_index(h3_index)
        if cell:
            zone.h3_cells.add(cell)
            update_cell_risk(h3_index, risk, confidence)
    
    if created:
        transition_zone_state(zone, 'monitoring', 'Weather-triggered zone created')
    
    return zone


# ============================================================
# Trigger 2: Community Reports
# ============================================================

def generate_zone_from_reports(report_ids=None, hours=24, radius_m=REPORT_CLUSTER_RADIUS_M):
    """
    Generate a temporary flood zone from clustered community reports.
    """
    cutoff = timezone.now() - timedelta(hours=hours)
    reports = IncidentReport.objects.filter(created_at__gte=cutoff, status='verified')
    if report_ids:
        reports = reports.filter(id__in=report_ids)
    
    if reports.count() < MIN_REPORTS_FOR_ZONE:
        return None
    
    from django.contrib.gis.geos import MultiPoint
    points = [r.location for r in reports if r.location]
    if len(points) < MIN_REPORTS_FOR_ZONE:
        return None
    
    try:
        multipoint = MultiPoint(*points)
        centroid = multipoint.centroid
        lat, lon = centroid.y, centroid.x
        
        distances = [p.distance(centroid) for p in points]
        max_dist = max(distances) if distances else radius_m
        radius_m = max(radius_m, max_dist * 2)
        
        avg_severity = sum(r.severity for r in reports) / len(reports)
        confidence = min(0.9, 0.4 + (len(reports) * 0.05) + (avg_severity * 0.1))
        
        zone_name = f"Community Zone {lat:.3f},{lon:.3f}"
        polygon = _polygon_from_point(lat, lon, radius_m)
        
        zone, created = DynamicZone.objects.get_or_create(
            name=zone_name,
            creation_source='community',
            defaults={
                'state': 'new',
                'geometry': polygon,
                'risk_score': min(0.95, 0.3 + (avg_severity * 0.12)),
                'confidence': confidence,
                'cause': f"{len(reports)} community reports in {hours}h window",
                'evidence': {
                    'report_count': len(reports),
                    'avg_severity': avg_severity,
                    'report_ids': [r.id for r in reports[:20]],
                },
                'population_exposed': estimate_population_in_polygon(polygon),
                'expires_at': timezone.now() + timedelta(hours=12),
            }
        )
        
        if not created:
            zone.risk_score = min(0.95, zone.risk_score + 0.05)
            zone.confidence = max(zone.confidence, confidence)
            zone.evidence['report_count'] = len(reports)
            zone.expires_at = timezone.now() + timedelta(hours=12)
            zone.save()
        
        h3_indices = _h3_cells_for_polygon(polygon, 7)
        for h3_index in h3_indices:
            cell = _h3_cell_from_index(h3_index)
            if cell:
                zone.h3_cells.add(cell)
                update_cell_risk(h3_index, zone.risk_score, zone.confidence)
        
        if created:
            transition_zone_state(zone, 'active', f'Generated from {len(reports)} community reports')
        
        return zone
    except Exception as e:
        logger.error(f"Failed to generate zone from reports: {e}")
        return None


# ============================================================
# Trigger 3: River Discharge
# ============================================================

def generate_zone_from_discharge(zone, discharge_value, forecast_hours=0):
    """
    Generate or expand a flood corridor based on river discharge.
    """
    try:
        geom = getattr(zone, 'geometry', None) or getattr(zone, 'polygon', None)
        if geom is None:
            raise AttributeError("Zone has neither geometry nor polygon")
        lat = geom.centroid.y
        lon = geom.centroid.x
        
        risk = calculate_feature_risk({'river_discharge': discharge_value, 'sources_available': 2})
        confidence = 0.7
        
        upstream_cells = _get_upstream_h3_cells(zone, forecast_hours)
        downstream_cells = _get_downstream_h3_cells(zone, forecast_hours)
        
        polygon = zone.geometry
        if downstream_cells:
            try:
                import h3
                coords = []
                for idx in downstream_cells[:20]:
                    geo = h3.cells_to_geo([idx])
                    if geo and geo.get('coordinates'):
                        coords.extend(geo['coordinates'][0][:5])
                if coords:
                    from django.contrib.gis.geos import MultiPoint
                    mp = MultiPoint([(c[0], c[1]) for c in coords])
                    hull = mp.convex_hull
                    if hull.area > 0:
                        polygon = polygon.union(hull.buffer(0.001))
            except Exception:
                pass
        
        zone.risk_score = max(zone.risk_score, risk)
        zone.confidence = max(zone.confidence, confidence)
        zone.geometry = polygon
        zone.cause = f"River discharge: {discharge_value:.1f} m³/s"
        zone.save()
        
        for cell_index in upstream_cells + downstream_cells:
            update_cell_risk(cell_index, risk, confidence)
            cell_obj, _ = H3Cell.objects.get_or_create(
                h3_index=cell_index,
                defaults={'resolution': 7, 'centroid_lat': 0.0, 'centroid_lon': 0.0}
            )
            zone.h3_cells.add(cell_obj)
        
        if zone.risk_score >= 0.7 and zone.state not in ['escalated']:
            transition_zone_state(zone, 'escalated', f'Discharge {discharge_value:.1f} exceeded threshold')
        
        return zone
    except Exception as e:
        logger.error(f"Failed to generate zone from discharge: {e}")
        return None


def _get_upstream_h3_cells(zone, hours=0):
    try:
        import h3
        center = h3.latlng_to_cell(zone.geometry.centroid.y, zone.geometry.centroid.x, 7)
        return h3.grid_disk(center, 2)
    except Exception:
        return []


def _get_downstream_h3_cells(zone, hours=0):
    try:
        import h3
        center = h3.latlng_to_cell(zone.geometry.centroid.y, zone.geometry.centroid.x, 7)
        return h3.grid_disk(center, 3)
    except Exception:
        return []


# ============================================================
# Trigger 4: Extreme Rainfall
# ============================================================

def generate_zone_from_rainfall(lat, lon, rainfall_mm, duration_hours=1, zone_name=None):
    """
    Merge neighboring high-risk H3 cells into a rainfall flood zone.
    """
    if zone_name is None:
        zone_name = _generate_zone_name(lat, lon, 'rainfall')
    
    risk = min(0.95, 0.2 + (rainfall_mm / 100.0))
    confidence = 0.6 if duration_hours >= 3 else 0.5
    polygon = _polygon_from_point(lat, lon, 500)
    
    zone, created = DynamicZone.objects.get_or_create(
        name=zone_name,
        creation_source='rainfall',
        defaults={
            'state': 'new',
            'geometry': polygon,
            'risk_score': risk,
            'confidence': confidence,
            'cause': f"Extreme rainfall: {rainfall_mm}mm in {duration_hours}h",
            'evidence': {'rainfall_mm': rainfall_mm, 'duration_hours': duration_hours},
            'expires_at': timezone.now() + timedelta(hours=8),
        }
    )
    
    if not created:
        zone.risk_score = max(zone.risk_score, risk)
        zone.confidence = max(zone.confidence, confidence)
        zone.cause = f"Extreme rainfall: {rainfall_mm}mm in {duration_hours}h"
        zone.expires_at = timezone.now() + timedelta(hours=8)
        zone.save()
    
    h3_indices = _h3_cells_for_polygon(polygon, 7)
    for h3_index in h3_indices:
        cell = _h3_cell_from_index(h3_index)
        if cell:
            zone.h3_cells.add(cell)
            update_cell_risk(h3_index, risk, confidence)
    
    if created:
        transition_zone_state(zone, 'monitoring', f'Rainfall {rainfall_mm}mm triggered zone')
    
    return zone


# ============================================================
# Trigger 5: Satellite/Open Data
# ============================================================

def enhance_zone_with_satellite(zone, water_extent_km2=None, flood_percentage=None):
    """
    Increase zone confidence and expand extent based on satellite data.
    """
    if water_extent_km2 is None:
        return zone
    
    confidence = min(0.95, zone.confidence + 0.2)
    zone.confidence = confidence
    zone.evidence['water_extent_km2'] = water_extent_km2
    if flood_percentage is not None:
        zone.evidence['flood_percentage'] = flood_percentage
        zone.risk_score = max(zone.risk_score, min(0.95, flood_percentage))
    zone.save()
    
    for cell in zone.h3_cells.all():
        update_cell_risk(cell.h3_index, zone.risk_score, confidence)
    
    return zone


# ============================================================
# Trigger 6: Authority Input
# ============================================================

def create_authority_zone(name, polygon, risk_score, confidence=1.0, expires_hours=None, user=None):
    """
    Create a manual zone from authority input. Overrides automatic zones.
    """
    zone, created = DynamicZone.objects.get_or_create(
        name=name,
        creation_source='authority',
        defaults={
            'state': 'active',
            'geometry': polygon,
            'risk_score': risk_score,
            'confidence': confidence,
            'authority_override': True,
            'expires_at': timezone.now() + timedelta(hours=expires_hours) if expires_hours else None,
        }
    )
    
    if not created:
        zone.risk_score = risk_score
        zone.confidence = confidence
        zone.authority_override = True
        zone.save()
    
    h3_indices = _h3_cells_for_polygon(polygon, 7)
    for h3_index in h3_indices:
        cell = _h3_cell_from_index(h3_index)
        if cell:
            zone.h3_cells.add(cell)
            update_cell_risk(h3_index, risk_score, confidence)
    
    if created:
        transition_zone_state(zone, 'active', 'Authority-created zone', triggered_by=user.username if user else 'system')
    
    return zone


# ============================================================
# Zone Merge Logic
# ============================================================

def merge_zones(zone_a, zone_b, user=None):
    """
    Merge two neighboring zones with similar characteristics.
    """
    if zone_a.id == zone_b.id:
        return zone_a
    
    if not _are_zones_mergeable(zone_a, zone_b):
        return None
    
    merged_polygon = zone_a.geometry.union(zone_b.geometry)
    if isinstance(merged_polygon, MultiPolygon):
        merged_polygon = merged_polygon.convex_hull
    
    merged_risk = max(zone_a.risk_score, zone_b.risk_score)
    merged_confidence = min(zone_a.confidence, zone_b.confidence)
    merged_name = f"Merged Zone ({zone_a.name} + {zone_b.name})"
    
    merged_zone = DynamicZone.objects.create(
        name=merged_name,
        state='monitoring',
        creation_source='merged',
        geometry=merged_polygon,
        risk_score=merged_risk,
        confidence=merged_confidence,
        cause=f"Merged from {zone_a.name} and {zone_b.name}",
        evidence={
            'merged_from': [zone_a.id, zone_b.id],
            'zone_a_risk': zone_a.risk_score,
            'zone_b_risk': zone_b.risk_score,
        },
    )
    
    merged_zone.h3_cells.add(*zone_a.h3_cells.all())
    merged_zone.h3_cells.add(*zone_b.h3_cells.all())
    merged_zone.merged_from.add(zone_a, zone_b)
    
    for cell in merged_zone.h3_cells.all():
        update_cell_risk(cell.h3_index, merged_risk, merged_confidence)
    
    zone_a.state = 'archived'
    zone_b.state = 'archived'
    zone_a.save(update_fields=['state', 'updated_at'])
    zone_b.save(update_fields=['state', 'updated_at'])
    
    transition_zone_state(merged_zone, 'monitoring', f'Merged {zone_a.name} and {zone_b.name}', triggered_by=user.username if user else 'system')
    
    return merged_zone


def _are_zones_mergeable(zone_a, zone_b):
    """
    Check if two zones should be merged.
    Conditions:
    - Similar risk score (within 0.15)
    - Similar confidence (within 0.2)
    - Adjacent or overlapping geometries
    - Same or similar creation source
    """
    if abs(zone_a.risk_score - zone_b.risk_score) > 0.15:
        return False
    if abs(zone_a.confidence - zone_b.confidence) > 0.2:
        return False
    if zone_a.creation_source != zone_b.creation_source:
        return False
    if not zone_a.geometry.intersects(zone_b.geometry):
        return False
    return True


# ============================================================
# Zone Split Logic
# ============================================================

def split_zone(zone, split_points=None):
    """
    Split a zone with heterogeneous risk into multiple zones.
    """
    if split_points is None:
        split_points = _detect_split_points(zone)
    
    if not split_points or len(split_points) < 2:
        return [zone]
    
    new_zones = []
    for i, point in enumerate(split_points):
        next_point = split_points[i + 1] if i + 1 < len(split_points) else None
        if next_point is None:
            continue
        
        try:
            sub_polygon = _extract_sub_polygon(zone.geometry, point, next_point)
            if sub_polygon.area < 1e-10:
                continue
            
            sub_risk = _calculate_sub_zone_risk(zone, sub_polygon)
            sub_name = f"{zone.name} - Part {i+1}"
            
            new_zone = DynamicZone.objects.create(
                name=sub_name,
                state='monitoring',
                creation_source='split',
                geometry=sub_polygon,
                risk_score=sub_risk,
                confidence=zone.confidence,
                cause=f"Split from {zone.name}",
                evidence=zone.evidence.copy(),
                parent_zone=zone,
            )
            
            for cell in zone.h3_cells.all():
                try:
                    if sub_polygon.intersects(Point(cell.centroid_lon, cell.centroid_lat, srid=4326)):
                        new_zone.h3_cells.add(cell)
                        update_cell_risk(cell.h3_index, sub_risk, zone.confidence)
                except Exception:
                    continue
            
            new_zones.append(new_zone)
        except Exception as e:
            logger.warning(f"Failed to create split zone {i}: {e}")
            continue
    
    if new_zones:
        zone.state = 'archived'
        zone.save(update_fields=['state', 'updated_at'])
    
    return new_zones


def _detect_split_points(zone):
    try:
        import h3
        center_lat = zone.geometry.centroid.y
        center_lon = zone.geometry.centroid.x
        center_cell = h3.latlng_to_cell(center_lat, center_lon, 7)
        neighbors = h3.grid_disk(center_cell, 2)
        
        high_risk = []
        low_risk = []
        for n in neighbors:
            risk = get_cell_risk(n)
            if risk >= HIGH_RISK_THRESHOLD:
                high_risk.append(n)
            elif risk <= MEDIUM_RISK_THRESHOLD:
                low_risk.append(n)
        
        if high_risk and low_risk:
            return [center_cell] + high_risk[:3] + low_risk[:3]
        return []
    except Exception:
        return []


def _extract_sub_polygon(polygon, start_cell, end_cell):
    try:
        import h3
        coords1 = h3.cells_to_geo([start_cell])['coordinates'][0]
        coords2 = h3.cells_to_geo([end_cell])['coordinates'][0]
        
        mid_lat = (coords1[0][1] + coords2[0][1]) / 2
        mid_lon = (coords1[0][0] + coords2[0][0]) / 2
        
        from django.contrib.gis.geos import Point
        center = Point(mid_lon, mid_lat, srid=4326)
        return polygon.intersection(center.buffer(0.01))
    except Exception:
        return polygon


def _calculate_sub_zone_risk(zone, sub_polygon):
    try:
        from django.contrib.gis.geos import Point
        center = sub_polygon.centroid
        lat, lon = center.y, center.x
        risk, _, _ = _risk_for_point(lat, lon)
        return max(0.0, min(1.0, risk))
    except Exception:
        return zone.risk_score * 0.8


# ============================================================
# Zone Retirement
# ============================================================

def retire_expired_zones():
    """
    Retire zones that have passed their expiry time.
    """
    now = timezone.now()
    expired = DynamicZone.objects.filter(
        state__in=['new', 'monitoring', 'active', 'stabilizing'],
        expires_at__lte=now
    )
    
    retired = 0
    for zone in expired:
        transition_zone_state(zone, 'inactive', 'Zone expired')
        zone.save(update_fields=['state', 'updated_at'])
        retired += 1
    
    logger.info(f"Retired {retired} expired dynamic zones")
    return retired


def archive_inactive_zones(days=7):
    """
    Archive zones that have been inactive for more than N days.
    """
    cutoff = timezone.now() - timedelta(days=days)
    inactive = DynamicZone.objects.filter(state='inactive', updated_at__lte=cutoff)
    
    archived = 0
    for zone in inactive:
        transition_zone_state(zone, 'archived', 'Auto-archived after inactivity')
        zone.archived_at = timezone.now()
        zone.save(update_fields=['state', 'archived_at', 'updated_at'])
        archived += 1
    
    logger.info(f"Archived {archived} inactive dynamic zones")
    return archived


# ============================================================
# Utilities
# ============================================================

def estimate_population_in_polygon(polygon):
    try:
        admin = AdministrativeBoundary.objects.filter(
            boundary_type__in=['village', 'ward', 'constituency'],
            geometry__intersects=polygon
        ).first()
        if admin and admin.metadata:
            return admin.metadata.get('population', 0)
        return 0
    except Exception:
        return 0


def _build_cause_text(features):
    if not features:
        return 'No data available'
    causes = []
    if features.get('river_discharge', 0) > 10:
        causes.append(f"High river discharge ({features['river_discharge']:.1f} m³/s)")
    if features.get('rainfall_1h_mm', 0) > 5:
        causes.append(f"Heavy rainfall ({features['rainfall_1h_mm']:.1f}mm)")
    if features.get('precip_intensity', 0) > 2:
        causes.append(f"High precipitation intensity ({features['precip_intensity']:.1f}mm/hr)")
    if features.get('water_extent_km2', 0) > 0.5:
        causes.append(f"Satellite water detection ({features['water_extent_km2']:.1f} km²)")
    return '; '.join(causes) if causes else 'Elevated multi-source risk indicators'
