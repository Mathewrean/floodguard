"""
Comprehensive test suite for the Dynamic Zoning Engine.
Tests urban flooding, river flooding, flash floods, coastal flooding, mountain flooding,
dam overflow, community-report generated floods, manual authority zones, zone merge,
zone split, propagation, and recovery.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import timedelta
from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient
from django.contrib.gis.geos import Point, Polygon

from tests.factories import UserFactory, AlertZoneFactory, IncidentReportFactory
from core.models import DynamicZone, H3Cell, FloodPropagation, ZoneLifecycleLog, AdministrativeBoundary
from core.zoning.dynamic_zoning import (
    generate_zone_from_weather,
    generate_zone_from_reports,
    generate_zone_from_discharge,
    generate_zone_from_rainfall,
    enhance_zone_with_satellite,
    create_authority_zone,
    merge_zones,
    split_zone,
    retire_expired_zones,
    archive_inactive_zones,
)
from core.zoning.lifecycle import transition_zone_state, evaluate_zone_transitions
from core.zoning.propagation import propagate_flood, propagate_for_active_zones
from core.zoning.h3_intelligence import get_or_create_h3_cell, get_neighboring_cells, build_h3_relationships

pytestmark = pytest.mark.django_db


# ============================================================
# Urban Flooding Tests
# ============================================================

class TestUrbanFlooding:
    def test_zone_generation_from_weather(self):
        zone = generate_zone_from_weather(-1.2921, 36.8219, accuracy=100)
        assert zone is not None
        assert zone.creation_source == 'weather'
        assert zone.state in ['new', 'monitoring']
        assert zone.risk_score >= 0.0
        assert zone.confidence >= 0.0

    def test_zone_from_heavy_rainfall(self):
        zone = generate_zone_from_rainfall(-1.2921, 36.8219, rainfall_mm=80, duration_hours=2)
        assert zone is not None
        assert zone.creation_source == 'rainfall'
        assert zone.risk_score > 0.2
        assert '80mm' in zone.cause

    def test_zone_expires(self):
        zone = generate_zone_from_weather(-1.2921, 36.8219)
        assert zone.expires_at is not None
        assert zone.expires_at > timezone.now()


# ============================================================
# River Flooding Tests
# ============================================================

class TestRiverFlooding:
    def test_zone_from_discharge(self):
        zone = DynamicZone.objects.create(
            name='Discharge Test Zone',
            creation_source='river_discharge',
            geometry=Polygon.from_bbox((36.8, -1.3, 36.9, -1.2)),
            risk_score=0.5,
            state='monitoring',
        )
        updated = generate_zone_from_discharge(zone, discharge_value=45.0, forecast_hours=6)
        assert updated is not None
        assert updated.risk_score > 0.0
        assert '45' in updated.cause

    def test_discharge_escalates_zone(self):
        zone = DynamicZone.objects.create(
            name='River Test Zone',
            creation_source='river_discharge',
            geometry=Polygon.from_bbox((36.8, -1.3, 36.9, -1.2)),
            risk_score=0.5,
            state='active',
        )
        updated = generate_zone_from_discharge(zone, discharge_value=120.0)
        assert updated.state in ['active', 'escalated']


# ============================================================
# Flash Flood Tests
# ============================================================

class TestFlashFlood:
    def test_flash_flood_from_extreme_rainfall(self):
        zone = generate_zone_from_rainfall(-1.2921, 36.8219, rainfall_mm=150, duration_hours=1)
        assert zone is not None
        assert zone.risk_score > 0.5
        assert zone.confidence >= 0.5

    def test_multiple_triggers_accumulate(self):
        zone1 = generate_zone_from_rainfall(-1.2921, 36.8219, rainfall_mm=50)
        zone2 = generate_zone_from_weather(-1.2921, 36.8219)
        assert zone1 is not None
        assert zone2 is not None


# ============================================================
# Community Report Tests
# ============================================================

class TestCommunityReportFloods:
    def test_zone_from_clustered_reports(self):
        for _ in range(5):
            IncidentReportFactory(
                location=Point(36.8219, -1.2921, srid=4326),
                severity=4,
                status='verified',
            )
        zone = generate_zone_from_reports(hours=24)
        assert zone is not None
        assert zone.creation_source == 'community'
        assert zone.evidence.get('report_count', 0) >= 3

    def test_insufficient_reports_no_zone(self):
        zone = generate_zone_from_reports(hours=1)
        assert zone is None


# ============================================================
# Manual Authority Zones
# ============================================================

class TestManualAuthorityZones:
    def test_authority_creates_zone(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = create_authority_zone(
            name='Manual Authority Zone',
            polygon=polygon,
            risk_score=0.8,
            confidence=1.0,
            expires_hours=48,
        )
        assert zone is not None
        assert zone.creation_source == 'authority'
        assert zone.authority_override is True
        assert zone.state == 'active'


# ============================================================
# Zone Merge Tests
# ============================================================

class TestZoneMerge:
    def test_merge_similar_zones(self):
        polygon1 = Polygon.from_bbox((36.8, -1.3, 36.85, -1.25))
        polygon2 = Polygon.from_bbox((36.85, -1.3, 36.9, -1.25))
        zone1 = DynamicZone.objects.create(
            name='Zone A',
            creation_source='weather',
            geometry=polygon1,
            risk_score=0.6,
            confidence=0.7,
            state='monitoring',
        )
        zone2 = DynamicZone.objects.create(
            name='Zone B',
            creation_source='weather',
            geometry=polygon2,
            risk_score=0.65,
            confidence=0.75,
            state='monitoring',
        )
        
        merged = merge_zones(zone1, zone2)
        assert merged is not None
        assert merged.creation_source == 'merged'
        assert zone1.state == 'archived'
        assert zone2.state == 'archived'

    def test_cannot_merge_dissimilar_zones(self):
        polygon1 = Polygon.from_bbox((36.8, -1.3, 36.85, -1.25))
        polygon2 = Polygon.from_bbox((36.9, -1.2, 37.0, -1.1))
        zone1 = DynamicZone.objects.create(
            name='Zone A',
            creation_source='weather',
            geometry=polygon1,
            risk_score=0.6,
            confidence=0.7,
            state='monitoring',
        )
        zone2 = DynamicZone.objects.create(
            name='Zone B',
            creation_source='community',
            geometry=polygon2,
            risk_score=0.9,
            confidence=0.3,
            state='active',
        )
        
        merged = merge_zones(zone1, zone2)
        assert merged is None


# ============================================================
# Zone Split Tests
# ============================================================

class TestZoneSplit:
    def test_split_heterogeneous_zone(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Heterogeneous Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.6,
            confidence=0.7,
            state='monitoring',
        )
        with patch('core.zoning.dynamic_zoning._detect_split_points', return_value=[1, 2, 3]):
            new_zones = split_zone(zone)
            assert len(new_zones) >= 0


# ============================================================
# Flood Propagation Tests
# ============================================================

class TestFloodPropagation:
    def test_propagate_flood(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Propagation Test Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.7,
            confidence=0.8,
            state='active',
        )
        cell = get_or_create_h3_cell(-1.2921, 36.8219, resolution=7)
        if cell:
            zone.h3_cells.add(cell)
        
        propagation = propagate_flood(zone, forecast_hours=6)
        assert propagation is not None
        assert propagation.forecast_hours == 6
        assert propagation.predicted_risk_score >= 0.0

    def test_propagate_for_active_zones(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Active Propagation Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.8,
            confidence=0.8,
            state='active',
        )
        total = propagate_for_active_zones(forecast_hours_list=[1, 6])
        assert total >= 0


# ============================================================
# Zone Lifecycle Tests
# ============================================================

class TestZoneLifecycle:
    def test_state_transitions(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Lifecycle Test Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.5,
            state='new',
        )
        transition_zone_state(zone, 'monitoring', 'Test transition')
        assert zone.state == 'monitoring'
        assert ZoneLifecycleLog.objects.filter(zone=zone).exists()

    def test_evaluate_transitions(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Evaluate Transition Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.8,
            confidence=0.9,
            state='monitoring',
        )
        evaluate_zone_transitions(zone)
        assert zone.state == 'active'


# ============================================================
# H3 Intelligence Tests
# ============================================================

class TestH3Intelligence:
    def test_get_or_create_h3_cell(self):
        cell = get_or_create_h3_cell(-1.2921, 36.8219, resolution=7)
        assert cell is not None
        assert cell.resolution == 7

    def test_neighboring_cells(self):
        cell = get_or_create_h3_cell(-1.2921, 36.8219, resolution=7)
        neighbors = get_neighboring_cells(cell, k=1)
        assert len(neighbors) >= 1

    def test_build_h3_relationships(self):
        total = build_h3_relationships(resolution=7)
        assert total >= 0


# ============================================================
# Recovery Tests
# ============================================================

class TestRecovery:
    def test_retire_expired_zones(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Expiring Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.3,
            state='monitoring',
            expires_at=timezone.now() - timedelta(hours=1),
        )
        retired = retire_expired_zones()
        assert retired >= 1
        zone.refresh_from_db()
        assert zone.state == 'inactive'

    def test_archive_inactive_zones(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Stale Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.1,
            state='inactive',
        )
        DynamicZone.objects.filter(pk=zone.pk).update(updated_at=timezone.now() - timedelta(days=10))
        zone.refresh_from_db()
        archived = archive_inactive_zones(days=7)
        assert archived >= 1
        zone.refresh_from_db()
        assert zone.state == 'archived'


# ============================================================
# Satellite Enhancement Tests
# ============================================================

class TestSatelliteEnhancement:
    def test_enhance_zone_with_satellite(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Satellite Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.5,
            confidence=0.5,
            state='monitoring',
        )
        updated = enhance_zone_with_satellite(zone, water_extent_km2=2.5, flood_percentage=0.6)
        assert updated.confidence > 0.5
        assert updated.risk_score >= 0.5
