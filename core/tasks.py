from celery import shared_task
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.utils import timezone
from core.models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile
import requests
import json
import redis
from django.conf import settings
import logging
from core.alerts.email import send_email_alert
from core.data_sources.aggregator import build_risk_feature_vector

logger = logging.getLogger(__name__)

# Initialize Redis connection
redis_client = redis.Redis.from_url(settings.REDIS_URL)

@shared_task
def fetch_flood_api(zone_id):
    """
    Fetch multi-source flood data for a given zone and create a FloodReading.
    """
    try:
        zone = AlertZone.objects.get(id=zone_id)
    except AlertZone.DoesNotExist:
        logger.error(f"AlertZone with id {zone_id} does not exist.")
        return

    centroid = zone.polygon.centroid
    lat, lon = centroid.y, centroid.x

    try:
        features = build_risk_feature_vector(lat, lon, zone.name)
        discharge = float(features.get('river_discharge') or 0)

        from core.analytics.scoring import calculate_risk_score
        risk_score = calculate_risk_score(features)
        source_count = int(features.get('sources_available', 0) or 0)
        source_name = 'multi_source' if source_count > 1 else 'open_meteo'
        FloodReading.objects.create(
            location=Point(lon, lat, srid=4326),
            water_level_metres=round(discharge / 100.0, 2),
            risk_score=risk_score,
            source=source_name,
            verified=source_count > 0,
            metadata=features,
        )
        zone.risk_score = risk_score
        zone.save(update_fields=['risk_score', 'updated_at'])
        logger.info("Successfully fetched and stored multi-source flood data for zone %s", zone.name)

    except Exception as e:
        logger.error(f"Error fetching flood data for zone {zone.id}: {str(e)}")
        return

@shared_task
def run_risk_scoring(reading_id):
    """
    Calculate risk score for a given FloodReading and update the record.
    """
    try:
        reading = FloodReading.objects.select_related().get(id=reading_id)
    except FloodReading.DoesNotExist:
        logger.error(f"FloodReading with id {reading_id} does not exist.")
        return

    # Find the zone that contains this reading
    try:
        zone = AlertZone.objects.get(polygon__covers=reading.location)
    except AlertZone.DoesNotExist:
        logger.warning(f"No zone found for reading at {reading.location}")
        return

    try:
        if reading.metadata:
            from core.analytics.scoring import calculate_risk_score
            risk_score = calculate_risk_score(reading.metadata)
        else:
            import datetime

            import joblib
            import numpy as np

            from django.conf import settings

            two_hours_ago = timezone.now() - datetime.timedelta(hours=2)
            latest_reading = FloodReading.objects.filter(
                location__coveredby=zone.polygon,
                timestamp__gte=two_hours_ago,
            ).order_by('-timestamp').first() or reading

            current_water_level = latest_reading.water_level_metres

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
                forecast_24h = current_water_level
                forecast_48h = current_water_level

            ninety_six_hours_ago = timezone.now() - datetime.timedelta(hours=96)
            recent_readings = FloodReading.objects.filter(
                location__coveredby=zone.polygon,
                timestamp__gte=ninety_six_hours_ago,
            ).order_by('-timestamp')[:96]

            if len(recent_readings) >= 10:
                rolling_24h_mean = np.mean([r.water_level_metres for r in recent_readings[:24]]) if len(recent_readings) >= 24 else current_water_level
                data_confidence = 'high'
            else:
                rolling_24h_mean = current_water_level
                data_confidence = 'low'

            try:
                model = joblib.load(settings.FLOOD_MODEL_PATH)
            except (FileNotFoundError, Exception):
                raise RuntimeError('ML model not available')

            now = timezone.now()
            features = [
                current_water_level,
                rolling_24h_mean,
                forecast_24h or current_water_level,
                forecast_48h or current_water_level,
                now.hour,
                now.weekday(),
            ]

            raw_score = model.predict([features])[0]
            if data_confidence == 'low':
                raw_score *= 0.75
            risk_score = max(0.0, min(1.0, raw_score))

        # The task keeps the specific reading in sync with the final score.
        reading.risk_score = risk_score
        reading.save(update_fields=['risk_score'])
        logger.info(f"Updated risk score for reading {reading.id} to {risk_score}")
    except Exception as e:
        logger.error(f"Error calculating risk score for reading {reading.id}: {str(e)}")

@shared_task
def dispatch_alerts(zone_id, risk_score):
    """
    Dispatch alerts for a given zone when risk score exceeds threshold.
    Sends SMS (primary) and Email (fallback) to authority users.
    """
    try:
        zone = AlertZone.objects.get(id=zone_id)
    except AlertZone.DoesNotExist:
        logger.error(f"AlertZone with id {zone_id} does not exist.")
        return

    # Check for manual alert override - if active, do not dispatch alerts
    if zone.is_override_active:
        logger.info(f"Alert dispatch skipped for zone {zone.name} due to active manual override")
        return

    # Build alert message
    from core.alerts.messages import build_alert_message
    message, severity_label = build_alert_message(zone, risk_score)

    # Get users within the zone (authority team)
    authority_users = User.objects.filter(
        groups__name='EmergencyTeam',
        is_active=True
    ).prefetch_related('profile').distinct()

    alert_logs_created = []
    
    for user in authority_users:
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            logger.warning(f"User {user.username} has no profile, skipping")
            continue
        
        # Create Redis key for deduplication (3 hours)
        redis_key = f"alert:{zone.id}:{user.id}"
        
        # Check if we have sent an alert in the last 3 hours
        if redis_client.exists(redis_key):
            logger.info(f"Alert deduplication: Skipping alert for user {user.username} in zone {zone.name}")
            continue
        
        delivery_success = False
        provider_message_id = None
        
        # Try SMS first if phone number available and SMS enabled
        if profile.phone_number and profile.sms_enabled:
            delivery_success, provider_message_id = _send_sms_alert(user, zone, message, redis_key)
        
        # Fallback to email if SMS failed or not available
        if not delivery_success and user.email:
            delivery_success = _send_email_alert_fallback(user, zone, message, severity_label)
            # Email doesn't have provider message ID like SMS
            provider_message_id = None
        
        # Create AlertLog record
        alert_log = AlertLog.objects.create(
            alert_zone=zone,
            message=message,
            channel='SMS' if delivery_success and profile.phone_number else 'Email',
            recipient_count=1,
            triggered_at=timezone.now(),
            delivery_status='sent' if delivery_success else 'failed',
            provider_message_id=provider_message_id,
        )
        alert_logs_created.append(alert_log)
    
    logger.info(f"Alert dispatch completed for zone {zone.name} with risk score {risk_score}. Sent to {len(alert_logs_created)} recipients")
    return alert_logs_created


def _send_sms_alert(user, zone, message, redis_key):
    """Send SMS via Africa's Talking API. Returns (success: bool, provider_message_id: str)"""
    try:
        if not getattr(settings, 'SMS_ENABLED', True):
            logger.info("SMS delivery disabled; skipping SMS to %s", user.username)
            return False, None
        if not settings.AFRICASTALKING_USERNAME or not settings.AFRICASTALKING_API_KEY:
            logger.warning("Africa's Talking credentials missing; skipping SMS to %s", user.username)
            return False, None

        profile = user.profile
        
        # Africa's Talking API endpoint
        sms_endpoint = "https://api.africastalking.com/version1/messaging"
        
        payload = {
            'username': settings.AFRICASTALKING_USERNAME,
            'to': profile.phone_number,
            'message': message[:159]  # Ensure within 160 chars
        }
        headers = {
            'apikey': settings.AFRICASTALKING_API_KEY,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        response = requests.post(sms_endpoint, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse response
        try:
            result = response.json()
            provider_message_id = result.get('SMSMessageData', {}).get('Recipients', [{}])[0].get('messageId', '')
        except Exception:
            provider_message_id = f"msg_{zone.id}_{user.id}_{int(timezone.now().timestamp())}"
        
        # Set Redis deduplication key (3 hours)
        redis_client.setex(redis_key, 3 * 60 * 60, 1)
        
        logger.info(f"SMS sent to {profile.phone_number} for zone {zone.name}")
        return True, provider_message_id
        
    except Exception as e:
        logger.error(f"Failed to send SMS to {user.username}: {str(e)}")
        return False, None


def _send_email_alert_fallback(user, zone, message, severity_label):
    """Send email alert as fallback when SMS fails or not available."""
    try:
        success = send_email_alert(
            recipient_email=user.email,
            subject=f"{severity_label} FLOOD ALERT - {zone.name}",
            template='emails/flood_alert.html',
            context={
                'zone_name': zone.name,
                'message': message,
                'severity': severity_label,
                'risk_score': None,  # Will be retrieved from zone if needed
            }
        )
        if success:
            logger.info(f"Email alert sent to {user.email} for zone {zone.name}")
        return success
    except Exception as e:
        logger.error(f"Failed to send email to {user.username}: {str(e)}")
        return False


@shared_task
def dispatch_manual_alert(zone_id, user_ids, channels, message):
    """
    Manually dispatch alerts to specific users in a zone.
    Used by admin panel for manual alert triggering.

    Args:
        zone_id: ID of the AlertZone
        user_ids: list of User IDs to alert
        channels: list of channels ['sms', 'email']
        message: custom alert message
    """
    try:
        zone = AlertZone.objects.get(id=zone_id)
    except AlertZone.DoesNotExist:
        logger.error(f"AlertZone with id {zone_id} does not exist.")
        return {'error': 'Zone not found'}

    if not user_ids:
        return {'error': 'No users specified'}

    alert_logs_created = []
    failed_count = 0

    for user_id in user_ids:
        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            logger.warning(f"User {user_id} not found or inactive, skipping")
            failed_count += 1
            continue

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            logger.warning(f"User {user.username} has no profile, skipping")
            failed_count += 1
            continue

        # For manual alerts, we don't use deduplication (test alerts bypass it)
        # But still create a Redis key to prevent accidental duplicate sends within 10 minutes
        redis_key = f"manual_alert:{zone.id}:{user.id}:{int(timezone.now().timestamp() // 600)}"

        delivery_success = False
        provider_message_id = None

        # Try SMS if requested
        if 'sms' in channels and profile.phone_number and profile.sms_enabled:
            delivery_success, provider_message_id = _send_sms_alert(user, zone, message, redis_key)

        # Try Email if requested and SMS didn't succeed (or email also requested)
        if 'email' in channels and user.email:
            email_success = _send_email_alert_fallback(user, zone, message, 'MANUAL')
            if email_success:
                delivery_success = True
            # If both were attempted, use last channel's status

        # Create AlertLog record
        channel_used = 'SMS' if 'sms' in channels and profile.phone_number else 'Email'
        alert_log = AlertLog.objects.create(
            alert_zone=zone,
            message=message,
            channel=channel_used,
            recipient_count=1,
            triggered_at=timezone.now(),
            delivery_status='sent' if delivery_success else 'failed',
            provider_message_id=provider_message_id,
        )
        alert_logs_created.append(alert_log)

        if not delivery_success:
            failed_count += 1

    logger.info(f"Manual alert dispatch completed for zone {zone.name}. Sent: {len(alert_logs_created) - failed_count}, Failed: {failed_count}")

    return {
        'zone_id': zone_id,
        'zone_name': zone.name,
        'total_targeted': len(user_ids),
        'success_count': len(alert_logs_created) - failed_count,
        'failed_count': failed_count,
        'logs_created': len(alert_logs_created)
    }
