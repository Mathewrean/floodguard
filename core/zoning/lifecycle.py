"""
Zone Lifecycle Manager
Handles automatic state transitions for dynamic flood zones.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from core.models import DynamicZone, ZoneLifecycleLog

logger = logging.getLogger(__name__)

ZONE_STATES = DynamicZone.ZONE_STATES

TRANSITIONS = {
    'new': ['monitoring', 'inactive'],
    'monitoring': ['active', 'stabilizing', 'inactive'],
    'active': ['escalated', 'stabilizing', 'inactive'],
    'escalated': ['active', 'stabilizing', 'inactive'],
    'stabilizing': ['inactive'],
    'inactive': ['archived'],
    'archived': [],
}

AUTO_TRANSITION_RULES = {
    'new': [('monitoring', lambda zone: True)],
    'monitoring': [
        ('active', lambda zone: zone.risk_score >= 0.7 and zone.confidence >= 0.5),
        ('inactive', lambda zone: zone.risk_score < 0.2),
    ],
    'active': [
        ('escalated', lambda zone: zone.risk_score >= 0.85),
        ('stabilizing', lambda zone: zone.risk_score < 0.5),
    ],
    'escalated': [
        ('active', lambda zone: zone.risk_score < 0.7),
        ('stabilizing', lambda zone: zone.risk_score < 0.5),
    ],
    'stabilizing': [('inactive', lambda zone: zone.risk_score < 0.3)],
    'inactive': [('archived', lambda zone: True)],
}


def transition_zone_state(zone, new_state, reason='', triggered_by='system'):
    current_state = zone.state
    if current_state == new_state:
        return zone

    allowed = TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        logger.warning(f"Invalid state transition for zone {zone.id}: {current_state} -> {new_state}")
        return zone

    ZoneLifecycleLog.objects.create(
        zone=zone,
        from_state=current_state,
        to_state=new_state,
        reason=reason,
        triggered_by=triggered_by,
    )

    zone.state = new_state
    zone.save(update_fields=['state', 'updated_at'])

    logger.info(f"Zone {zone.id} transitioned: {current_state} -> {new_state} ({reason})")
    return zone


def evaluate_zone_transitions(zone):
    current_state = zone.state
    if current_state not in AUTO_TRANSITION_RULES:
        return zone

    for target_state, condition in AUTO_TRANSITION_RULES.get(current_state, []):
        if condition(zone):
            return transition_zone_state(zone, target_state, f'Auto-transition from {current_state}')

    return zone


def process_lifecycle_for_all_zones():
    zones = DynamicZone.objects.exclude(state='archived')
    processed = 0
    for zone in zones:
        try:
            evaluate_zone_transitions(zone)
            processed += 1
        except Exception as e:
            logger.warning(f"Lifecycle processing failed for zone {zone.id}: {e}")

    logger.info(f"Processed lifecycle for {processed} zones")
    return processed
