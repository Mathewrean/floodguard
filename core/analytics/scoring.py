from django.utils import timezone
from core.models import FloodReading, AlertZone


class ModelNotAvailableError(Exception):
    pass


def calculate_discharge_risk(discharge):
    if discharge <= 0:
        return 0.05
    if discharge < 3:
        return 0.05 + (discharge / 3.0) * 0.20
    if discharge < 10:
        return 0.25 + ((discharge - 3.0) / 7.0) * 0.30
    if discharge < 30:
        return 0.55 + ((discharge - 10.0) / 20.0) * 0.25
    if discharge < 80:
        return 0.80 + ((discharge - 30.0) / 50.0) * 0.15
    return 0.98


def _clamp01(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _precipitation_component(features):
    candidates = [
        _clamp01((features.get('rainfall_1h_mm', 0) or 0) / 40.0),
        _clamp01((features.get('precip_intensity', 0) or 0) / 20.0),
        _clamp01((features.get('total_precip_mm', 0) or 0) / 100.0),
        _clamp01((features.get('nasa_precip', 0) or 0) / 20.0),
        _clamp01((features.get('precip_probability', 0) or 0) / 100.0),
        _clamp01((features.get('chance_of_rain', 0) or 0) / 100.0),
    ]
    return max(candidates) if candidates else 0.0


def calculate_feature_risk(features):
    discharge_norm = calculate_discharge_risk(features.get('river_discharge', 0))
    precipitation_component = _precipitation_component(features)
    humidity_factor = _clamp01((features.get('humidity', 50) or 0) / 100.0)
    sar_factor = _clamp01((features.get('water_extent_km2', 0) or 0) / 10.0)
    raw_score = (
        0.45 * discharge_norm +
        0.25 * precipitation_component +
        0.15 * humidity_factor +
        0.15 * sar_factor
    )
    return max(0.0, min(1.0, raw_score))


def calculate_risk_score(zone_or_features):
    """
    Calculate risk score from a feature vector or the latest reading for a zone.
    """
    if isinstance(zone_or_features, dict):
        return calculate_feature_risk(zone_or_features)

    zone_id = zone_or_features
    try:
        zone = AlertZone.objects.get(id=zone_id)
    except AlertZone.DoesNotExist:
        return 0.0

    centroid = zone.polygon.centroid
    lat, lon = centroid.y, centroid.x
    from core.data_sources.aggregator import build_risk_feature_vector

    features = build_risk_feature_vector(lat, lon, zone.name)
    risk_score = calculate_feature_risk(features)

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
