import datetime
import requests
import joblib
import numpy as np
from django.conf import settings
from django.utils import timezone
from core.models import FloodReading, AlertZone
from core.tasks import dispatch_alerts


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


def calculate_feature_risk(features):
    weighted_precip = (
        0.30 * features.get('rainfall_1h_mm', 0) +
        0.25 * features.get('precip_intensity', 0) +
        0.25 * features.get('total_precip_mm', 0) / 24 +
        0.20 * features.get('nasa_precip', 0)
    )
    discharge_norm = calculate_discharge_risk(features.get('river_discharge', 0))
    humidity_factor = features.get('humidity', 50) / 100
    sar_factor = min(features.get('water_extent_km2', 0) / 10, 1.0)
    raw_score = (
        0.45 * discharge_norm +
        0.25 * min(weighted_precip / 50, 1.0) +
        0.15 * humidity_factor +
        0.15 * sar_factor
    )
    if features.get('data_confidence') == 'low':
        raw_score *= 0.80
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

    # STEP 1 — Fetch latest FloodReading for zone
    two_hours_ago = timezone.now() - datetime.timedelta(hours=2)
    latest_reading = FloodReading.objects.filter(
        location__within=zone.polygon,
        timestamp__gte=two_hours_ago
    ).order_by('-timestamp').first()

    if not latest_reading:
        return 0.0  # No recent reading

    if latest_reading.metadata:
        risk_score = calculate_feature_risk(latest_reading.metadata)
        latest_reading.risk_score = risk_score
        latest_reading.save(update_fields=['risk_score'])
        if risk_score >= zone.risk_threshold:
            dispatch_alerts.delay(zone_id, risk_score)
        return risk_score

    current_water_level = latest_reading.water_level_metres

    # STEP 2 — Fetch Open-Meteo 7-day river discharge forecast
    centroid = zone.polygon.centroid
    lat, lon = centroid.y, centroid.x
    api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=river_discharge&past_days=0&forecast_days=7"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        hourly_discharge = data['hourly']['river_discharge']
        forecast_24h = hourly_discharge[24] if len(hourly_discharge) > 24 else None
        forecast_48h = hourly_discharge[48] if len(hourly_discharge) > 48 else None
    except (requests.RequestException, KeyError, IndexError):
        # Use last known or 0
        forecast_24h = current_water_level
        forecast_48h = current_water_level

    # STEP 3 — Calculate rolling 24h mean water level
    ninety_six_hours_ago = timezone.now() - datetime.timedelta(hours=96)
    recent_readings = FloodReading.objects.filter(
        location__within=zone.polygon,
        timestamp__gte=ninety_six_hours_ago
    ).order_by('-timestamp')[:96]

    if len(recent_readings) >= 10:
        rolling_24h_mean = np.mean([r.water_level_metres for r in recent_readings[:24]]) if len(recent_readings) >= 24 else current_water_level
        data_confidence = 'high'
    else:
        rolling_24h_mean = current_water_level
        data_confidence = 'low'

    # STEP 4 — Load ML model
    try:
        model = joblib.load(settings.FLOOD_MODEL_PATH)
    except (FileNotFoundError, Exception):
        raise ModelNotAvailableError("ML model not available")

    # STEP 5 — Assemble feature vector
    now = timezone.now()
    hour_of_day = now.hour
    day_of_week = now.weekday()
    features = [
        current_water_level,
        rolling_24h_mean,
        forecast_24h or current_water_level,
        forecast_48h or current_water_level,
        hour_of_day,
        day_of_week
    ]

    # STEP 6 — Run model.predict
    raw_score = model.predict([features])[0]

    # STEP 7 — Apply confidence penalty
    if data_confidence == 'low':
        raw_score *= 0.75

    # STEP 8 — Clamp
    risk_score = max(0.0, min(1.0, raw_score))

    # STEP 9 — Write back to FloodReading
    latest_reading.risk_score = risk_score
    latest_reading.save()

    # STEP 10 — Trigger dispatch if exceeds threshold
    if risk_score >= zone.risk_threshold:
        dispatch_alerts.delay(zone_id, risk_score)

    return risk_score
