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

logger = logging.getLogger(__name__)

# Initialize Redis connection
redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0)

@shared_task
def fetch_flood_api(zone_id):
    """
    Fetch flood data from Open-Meteo API for a given zone and create FloodReading records.
    """
    try:
        zone = AlertZone.objects.get(id=zone_id)
    except AlertZone.DoesNotExist:
        logger.error(f"AlertZone with id {zone_id} does not exist.")
        return

    centroid = zone.polygon.centroid
    lat, lon = centroid.y, centroid.x

    # Open-Meteo API endpoint for river discharge
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=river_discharge&past_days=0&forecast_days=7"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Process the hourly data
        times = data['hourly']['time']
        discharges = data['hourly']['river_discharge']
        
        for time_str, discharge in zip(times, discharges):
            # Convert time string to datetime
            timestamp = timezone.datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            
            # Create a FloodReading record
            FloodReading.objects.create(
                location=Point(lon, lat, srid=4326),  # Using centroid for simplicity
                water_level_metres=discharge,  # Using discharge as water level for now
                risk_score=0.0,  # Will be updated by risk scoring task
                source='open_meteo',
                verified=False,
                timestamp=timestamp
            )
        
        logger.info(f"Successfully fetched and stored flood data for zone {zone.name}")
        
    except Exception as e:
        logger.error(f"Error fetching flood data for zone {zone.id}: {str(e)}")

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
        zone = AlertZone.objects.get(polygon__contains=reading.location)
    except AlertZone.DoesNotExist:
        logger.warning(f"No zone found for reading at {reading.location}")
        return

    # Use the scoring function from analytics
    from core.analytics.scoring import calculate_risk_score
    try:
        risk_score = calculate_risk_score(zone.id)
        # The calculate_risk_score function already updates the latest reading in the zone
        # But we can also update this specific reading if needed
        reading.risk_score = risk_score
        reading.save(update_fields=['risk_score'])
        logger.info(f"Updated risk score for reading {reading.id} to {risk_score}")
    except Exception as e:
        logger.error(f"Error calculating risk score for reading {reading.id}: {str(e)}")

@shared_task
def dispatch_alerts(zone_id, risk_score):
    """
    Dispatch alerts for a given zone when risk score exceeds threshold.
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

    # Get users within the zone (simplified: for now, we'll alert all authority users)
    # In a real system, we would use spatial query to find users within the zone
    authority_users = User.objects.filter(
        groups__name='EmergencyTeam',
        is_active=True
    ).distinct()

    # For each user, check Redis deduplication
    for user in authority_users:
        # Create a Redis key for this user/zone pair
        redis_key = f"alert:{zone.id}:{user.id}"

        # Check if we have sent an alert in the last 3 hours
        if redis_client.exists(redis_key):
            logger.info(f"Alert deduplication: Skipping alert for user {user.username} in zone {zone.name}")
            continue

        # Send SMS via Africa's Talking
        try:
            from django.conf import settings
            import requests
            
            # Get user's phone number from profile
            try:
                phone_number = user.profile.phone_number
            except UserProfile.DoesNotExist:
                logger.warning(f"User {user.username} has no profile, skipping SMS")
                continue
            
            if not phone_number:
                logger.warning(f"User {user.username} has no phone number, skipping SMS")
                continue

            # Africa's Talking API endpoint
            sms_endpoint = "https://api.africastalking.com/version1/messaging"
            
            payload = {
                'username': getattr(settings, 'AFRICASTALKING_USERNAME', ''),
                'to': phone_number,
                'message': message[:159]  # Ensure within 160 chars
            }
            headers = {
                'apikey': getattr(settings, 'AFRICASTALKING_API_KEY', ''),
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            response = requests.post(sms_endpoint, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse response to get message ID
            try:
                result = response.json()
                provider_message_id = result.get('SMSMessageData', {}).get('Recipients', [{}])[0].get('messageId', '')
            except Exception:
                provider_message_id = f"msg_{zone.id}_{user.id}_{int(timezone.now().timestamp())}"
            
            # Set Redis key with 3-hour expiry
            redis_client.setex(redis_key, 3*60*60, 1)  # 3 hours in seconds
            
            # Create AlertLog record with delivery tracking
            alert_log = AlertLog.objects.create(
                alert_zone=zone,
                message=message,
                channel='SMS',
                recipient_count=1,
                triggered_at=timezone.now(),
                delivery_status='sent',
                provider_message_id=provider_message_id
            )
            
        except Exception as e:
            logger.error(f"Failed to send alert to user {user.username}: {str(e)}")
            # Create failed alert log
            AlertLog.objects.create(
                alert_zone=zone,
                message=message,
                channel='SMS',
                recipient_count=1,
                triggered_at=timezone.now(),
                delivery_status='failed'
            )

    logger.info(f"Alert dispatch completed for zone {zone.name} with risk score {risk_score}")