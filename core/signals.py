from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
from .models import UserProfile, FloodReading, AlertZone
from .alerts.messages import build_alert_message


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance, defaults={'role': 'citizen'})


@receiver(post_save, sender=FloodReading)
def flood_reading_updated(sender, instance, **kwargs):
    # Find the zone
    try:
        zone = AlertZone.objects.get(polygon__contains=instance.location)
    except AlertZone.DoesNotExist:
        return

    # Only proceed if we have a risk score
    if instance.risk_score is None:
        return

    # Build message for severity
    message, severity = build_alert_message(zone, instance.risk_score)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "flood_map_updates",
        {
            "type": "flood.update",
            "zone_id": zone.id,
            "risk_score": instance.risk_score,
            "severity": severity.lower(),
            "timestamp": instance.timestamp.isoformat(),
        }
    )