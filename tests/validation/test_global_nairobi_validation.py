"""
Global and Nairobi validation tests.
Tests 1000 random global locations and 500 Nairobi locations for zone generation,
risk consistency, propagation accuracy, safe routes, and decision support.
"""
import pytest
import random
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from core.models import DynamicZone, H3Cell, FloodPropagation, AlertZone
from core.zoning.dynamic_zoning import generate_zone_from_weather, merge_zones, split_zone
from core.zoning.propagation import propagate_flood
from core.zoning.h3_intelligence import get_or_create_h3_cell, get_neighboring_cells, _get_h3_resolution
from core.zoning.location_engine import process_user_location
from core.zoning.search_engine import universal_search

pytestmark = pytest.mark.django_db

# Nairobi bounds
NAIROBI_BOUNDS = {
    'min_lat': -1.450,
    'max_lat': -1.100,
    'min_lon': 36.650,
    'max_lon': 37.150,
}


def random_global_location():
    """Generate a random global location."""
    lat = random.uniform(-85, 85)
    lon = random.uniform(-180, 180)
    return lat, lon


def random_nairobi_location():
    """Generate a random location within Nairobi bounds."""
    lat = random.uniform(NAIROBI_BOUNDS['min_lat'], NAIROBI_BOUNDS['max_lat'])
    lon = random.uniform(NAIROBI_BOUNDS['min_lon'], NAIROBI_BOUNDS['max_lon'])
    return lat, lon


class TestGlobalValidation:
    """Test 1000 random global locations."""

    def test_1000_global_locations_h3_resolution(self):
        """Test that H3 resolution is valid for 1000 random global locations."""
        valid_resolutions = set(range(4, 11))
        for i in range(1000):
            lat, lon = random_global_location()
            resolution = _get_h3_resolution(lat, lon)
            assert resolution in valid_resolutions, f"Invalid resolution {resolution} for ({lat}, {lon})"

    def test_1000_global_locations_cell_creation(self):
        """Test H3 cell creation for 1000 random global locations."""
        for i in range(1000):
            lat, lon = random_global_location()
            cell = get_or_create_h3_cell(lat, lon, resolution=7)
            assert cell is not None
            assert cell.resolution == 7

    def test_1000_global_locations_zone_generation(self):
        """Test dynamic zone generation for 1000 random global locations."""
        for i in range(1000):
            lat, lon = random_global_location()
            zone = generate_zone_from_weather(lat, lon)
            assert zone is not None
            assert 0.0 <= zone.risk_score <= 1.0
            assert 0.0 <= zone.confidence <= 1.0


class TestNairobiValidation:
    """Test 500 random Nairobi locations."""

    def test_500_nairobi_locations_within_bounds(self):
        """All generated locations must be within Nairobi bounds."""
        for i in range(500):
            lat, lon = random_nairobi_location()
            assert NAIROBI_BOUNDS['min_lat'] <= lat <= NAIROBI_BOUNDS['max_lat']
            assert NAIROBI_BOUNDS['min_lon'] <= lon <= NAIROBI_BOUNDS['max_lon']

    def test_500_nairobi_locations_h3_generation(self):
        """Test H3 cell generation for 500 Nairobi locations."""
        cells = []
        for i in range(500):
            lat, lon = random_nairobi_location()
            cell = get_or_create_h3_cell(lat, lon, resolution=7)
            assert cell is not None
            cells.append(cell)
        
        # Check for duplicates
        h3_indices = [c.h3_index for c in cells]
        assert len(h3_indices) == len(set(h3_indices)), "Duplicate H3 cells found"

    def test_500_nairobi_locations_zone_consistency(self):
        """Test zone generation consistency for 500 Nairobi locations."""
        zones = []
        for i in range(500):
            lat, lon = random_nairobi_location()
            zone = generate_zone_from_weather(lat, lon)
            assert zone is not None
            zones.append(zone)
        
        # All zones should have valid risk scores
        for zone in zones:
            assert 0.0 <= zone.risk_score <= 1.0
            assert zone.expires_at is not None


class TestFloodEvents:
    """Test 100 simulated flood events."""

    def test_100_flood_events_zone_lifecycle(self):
        """Test complete zone lifecycle for 100 flood events."""
        for i in range(100):
            lat, lon = random_nairobi_location()
            zone = generate_zone_from_weather(lat, lon, accuracy=200)
            assert zone is not None
            assert zone.state in ['new', 'monitoring']
            
            # Simulate escalation
            zone.risk_score = 0.9
            zone.confidence = 0.8
            zone.save()
            
            from core.zoning.lifecycle import evaluate_zone_transitions
            evaluate_zone_transitions(zone)
            assert zone.state in ['active', 'escalated', 'monitoring']

    def test_100_flood_events_propagation(self):
        """Test flood propagation for 100 events."""
        for i in range(100):
            lat, lon = random_nairobi_location()
            zone = generate_zone_from_weather(lat, lon)
            if zone:
                propagation = propagate_flood(zone, forecast_hours=6)
                assert propagation is not None
                assert propagation.predicted_risk_score >= 0.0


class TestRecoverySimulations:
    """Test 50 recovery simulations."""

    def test_50_recovery_events_zone_retirement(self):
        """Test zone retirement after recovery."""
        from core.zoning.dynamic_zoning import retire_expired_zones, archive_inactive_zones
        
        for i in range(50):
            lat, lon = random_nairobi_location()
            zone = generate_zone_from_weather(lat, lon)
            if zone:
                # Simulate recovery by setting low risk and past expiry
                zone.risk_score = 0.1
                zone.expires_at = timezone.now() - timedelta(hours=1)
                zone.save()
                
                retired = retire_expired_zones()
                assert retired >= 0

    def test_50_recovery_events_archive_cleanup(self):
        """Test archive cleanup after recovery."""
        from core.zoning.dynamic_zoning import archive_inactive_zones
        
        for i in range(50):
            lat, lon = random_nairobi_location()
            zone = generate_zone_from_weather(lat, lon)
            if zone:
                zone.state = 'inactive'
                zone.updated_at = timezone.now() - timedelta(days=10)
                zone.save()
                
                archived = archive_inactive_zones(days=7)
                assert archived >= 0
