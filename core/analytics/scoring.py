"""
Multi-source weighted flood risk calculation.
All weights are configurable via settings/environment variables.
"""

from django.utils import timezone
from core.models import FloodReading, AlertZone
from .config import get_risk_weights, get_threshold_config


class ModelNotAvailableError(Exception):
    pass


def calculate_discharge_risk(discharge):
    """Risk score for river discharge (0-100+ m³/s)."""
    d = float(discharge or 0)
    thresholds = get_threshold_config()
    if d <= 0:
        return thresholds.get('low', 0.05)
    if d < 3:
        return 0.05 + (d / 3.0) * 0.20
    if d < 10:
        return 0.25 + ((d - 3.0) / 7.0) * 0.30
    if d < 30:
        return 0.55 + ((d - 10.0) / 20.0) * 0.25
    if d < 80:
        return 0.80 + ((d - 30.0) / 50.0) * 0.15
    return thresholds.get('critical', 0.95)


def _clamp01(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _precipitation_component(features, max_precip_1h=40.0, max_precip_intensity=20.0, max_total_precip=100.0, max_nasa=20.0):
    """Calculate precipitation risk component from multiple sources."""
    candidates = [
        _clamp01((features.get('rainfall_1h_mm', 0) or 0) / max_precip_1h),
        _clamp01((features.get('precip_intensity', 0) or 0) / max_precip_intensity),
        _clamp01((features.get('total_precip_mm', 0) or 0) / max_total_precip),
        _clamp01((features.get('nasa_precip', 0) or 0) / max_nasa),
        _clamp01((features.get('precip_probability', 0) or 0) / 100.0),
        _clamp01((features.get('chance_of_rain', 0) or 0) / 100.0),
    ]
    return max(candidates) if candidates else 0.0


def calculate_feature_risk(features):
    """Calculate risk score from feature vector using configurable weights."""
    weights = get_risk_weights()
    
    discharge_norm = calculate_discharge_risk(features.get('river_discharge', 0))
    precipitation_component = _precipitation_component(features)
    humidity_factor = _clamp01((features.get('humidity', 50) or 0) / 100.0)
    sar_factor = _clamp01((features.get('water_extent_km2', 0) or 0) / 10.0)
    
    raw_score = (
        weights.get('discharge_total_weight', 0.45) * discharge_norm +
        weights.get('precip_weight', 0.30) * precipitation_component +
        weights.get('env_total_weight', 0.25) * (
            weights.get('humidity_weight', 0.60) * humidity_factor +
            weights.get('sar_water_weight', 0.40) * sar_factor
        )
    )
    return max(0.0, min(1.0, raw_score))


def calculate_risk_score(zone_or_features):
    """
    Calculate risk score from a feature vector or the latest reading for a zone.
    Uses multi-source weighted scoring with configurable weights.
    """
    if isinstance(zone_or_features, dict):
        return _calculate_feature_risk(zone_or_features)

    zone_id = zone_or_features
    try:
        zone = AlertZone.objects.get(id=zone_id)
    except AlertZone.DoesNotExist:
        return 0.0

    centroid = zone.polygon.centroid
    lat, lon = centroid.y, centroid.x
    from core.data_sources.aggregator import build_risk_feature_vector

    try:
        features = build_risk_feature_vector(lat, lon, zone.name)
    except Exception:
        features = {'river_discharge': 0, 'sources_available': 0}

    risk_score = _calculate_feature_risk(features)

    latest_reading = FloodReading.objects.filter(location__coveredby=zone.polygon).order_by('-timestamp').first()
    if latest_reading:
        latest_reading.risk_score = risk_score
        if features:
            latest_reading.metadata = features
        latest_reading.save(update_fields=['risk_score', 'metadata'])

    if risk_score >= zone.risk_threshold:
        from core.tasks import dispatch_alerts
        dispatch_alerts.delay(zone_id, risk_score)

    return risk_score


def _calculate_feature_risk(features):
    """
    Multi-source weighted risk calculation.
    Considers: discharge, precipitation, humidity, satellite water extent.
    Applies confidence penalty for limited data sources.
    """
    weights = get_risk_weights()
    
    discharge = features.get('river_discharge', 0) or 0
    discharge_24h = features.get('discharge_24h', discharge)
    discharge_7d_max = features.get('discharge_7d_max', discharge)

    def score_discharge(d):
        d = float(d or 0)
        if d <= 0: return 0.05
        if d < 3: return round(0.05 + (d / 3.0) * 0.20, 3)
        if d < 10: return round(0.25 + ((d - 3.0) / 7.0) * 0.30, 3)
        if d < 30: return round(0.55 + ((d - 10.0) / 20.0) * 0.25, 3)
        if d < 80: return round(0.80 + ((d - 30.0) / 50.0) * 0.15, 3)
        return 0.98

    discharge_component = (
        weights.get('discharge_current', 0.50) * score_discharge(discharge) +
        weights.get('discharge_24h', 0.30) * score_discharge(discharge_24h) +
        weights.get('discharge_7d', 0.20) * score_discharge(discharge_7d_max)
    )

    rainfall_1h = (features.get('rainfall_1h_mm', 0) or 0) / 40.0
    precip = (features.get('precip_intensity', 0) or 0) / 20.0
    total_precip = (features.get('total_precip_mm', 0) or 0) / 24.0 / 100.0
    nasa_precip = (features.get('nasa_precip', 0) or 0) / 20.0
    precip_component = min(max(rainfall_1h, precip, total_precip, nasa_precip), 1.0)

    humidity = (features.get('humidity', 50) or 50) / 100.0
    sar_water = min((features.get('water_extent_km2', 0) or 0) / 10.0, 1.0)
    env_component = (weights.get('humidity_weight', 0.60) * humidity) + (weights.get('sar_water_weight', 0.40) * sar_water)

    raw_score = (
        weights.get('discharge_total_weight', 0.45) * discharge_component +
        weights.get('precip_weight', 0.30) * precip_component +
        weights.get('env_total_weight', 0.25) * env_component
    )

    sources_active = features.get('sources_available', 1) or 0
    if sources_active < 2:
        raw_score *= weights.get('confidence_single_source_penalty', 0.80)
    elif sources_active < 3:
        raw_score *= weights.get('confidence_two_source_penalty', 0.90)

    return max(0.0, min(1.0, round(raw_score, 3)))