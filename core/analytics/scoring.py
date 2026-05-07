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


def calculate_risk_score(zone_id):
    """
    Calculate risk score for the given zone_id following the specified logic.
    """
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