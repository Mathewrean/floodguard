"""
Signals for cache warming and automated maintenance.

These signals ensure that spatial aggregates and commonly accessed data
are pre-computed and cached to improve performance.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.contrib.gis.db.models import Extent
from django.conf import settings

from django.contrib.auth.models import User
from core.models import AlertZone, FloodReading, IncidentReport, UserProfile


CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours


# Auto-create UserProfile when a User is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create a UserProfile for each new User."""
    if created:
        UserProfile.objects.create(user=instance, role='citizen')


@receiver(post_save, sender=AlertZone)
def warm_zone_cache(sender, instance, created, **kwargs):
    """
    Pre-compute and cache spatial aggregates for a zone after save.
    caches:
    - zone:{id}:bounds - bounding box for quick map viewport queries
    - zones:extent - overall extent of all zones
    - zones:risk_summary - aggregated risk statistics
    """
    # Cache zone bounds
    bounds_key = f'zone:{instance.id}:bounds'
    if instance.polygon:
        extent = instance.polygon.extent  # (min_x, min_y, max_x, max_y)
        cache.set(bounds_key, extent, CACHE_TIMEOUT)

    # Invalidate and recompute global zones extent cache
    zones_extent_key = 'zones:extent'
    try:
        # Get combined extent of all zones
        aggregate = AlertZone.objects.aggregate(extent=Extent('polygon'))
        if aggregate['extent']:
            cache.set(zones_extent_key, aggregate['extent'], CACHE_TIMEOUT)
    except Exception:
        # If aggregation fails, just invalidate the old cache
        cache.delete(zones_extent_key)

    # Cache risk summary
    risk_summary_key = 'zones:risk_summary'
    try:
        from django.db.models import Count, Avg, Max, Min, Q
        summary = AlertZone.objects.aggregate(
            total_zones=Count('id'),
            high_risk=Count('id', filter=Q(risk_score__gt=0.7)),
            moderate_risk=Count('id', filter=Q(risk_score__gt=0.4, risk_score__lte=0.7)),
            safe=Count('id', filter=Q(risk_score__lte=0.4)),
            avg_risk=Avg('risk_score'),
            max_risk=Max('risk_score')
        )
        cache.set(risk_summary_key, summary, CACHE_TIMEOUT)
    except Exception:
        cache.delete(risk_summary_key)


@receiver(post_delete, sender=AlertZone)
def invalidate_zone_cache_on_delete(sender, instance, **kwargs):
    """Invalidate zone-related caches when a zone is deleted."""
    cache.delete(f'zone:{instance.id}:bounds')
    # Trigger recompute of global extent
    warm_zone_cache(sender, instance, created=False)


@receiver(post_save, sender=FloodReading)
def warm_readings_cache(sender, instance, created, **kwargs):
    """
    Cache latest readings per zone for quick dashboard display.
    Cache key: zone:{zone_id}:latest_reading
    """
    try:
        from django.contrib.gis.db.models import PointField
        from django.db.models.expressions import RawSQL

        # Find zones that contain this reading
        zones = AlertZone.objects.filter(polygon__contains=instance.location)
        for zone in zones:
            cache_key = f'zone:{zone.id}:latest_reading'
            # Store the reading ID and key data
            cache.set(cache_key, {
                'id': instance.id,
                'risk_score': instance.risk_score,
                'water_level': instance.water_level_metres,
                'timestamp': instance.timestamp.isoformat(),
                'source': instance.source,
                'verified': instance.verified,
            }, CACHE_TIMEOUT)
    except Exception:
        pass  # Silently fail cache operations


@receiver(post_save, sender=IncidentReport)
def warm_reports_cache(sender, instance, created, **kwargs):
    """
    Invalidate reports summary cache when reports change.
    """
    if created:
        # Invalidate reports counts cache
        cache.delete('reports:stats:recent')
