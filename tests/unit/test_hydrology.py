"""
Tests for Hydrological Propagation Engine.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import timedelta

from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from core.models import DynamicZone, FloodPropagation, H3Cell
from core.zoning.propagation import propagate_flood, propagate_for_active_zones
from core.zoning.propagation import (
    fetch_elevation_tile,
    fetch_dem_tile_batch,
    calculate_terrain_slope,
    calculate_flow_direction,
    calculate_flow_accumulation,
    detect_terrain_depressions,
    estimate_flood_depth,
    estimate_flood_velocity,
    simulate_river_overflow,
)

pytestmark = pytest.mark.django_db


class TestHydrologicalEngine:
    def test_fetch_elevation_tile(self):
        elev = fetch_elevation_tile(-1.2921, 36.8219)
        assert elev is None or isinstance(elev, (int, float))

    def test_calculate_terrain_slope(self):
        elevations = {i: 100 + i for i in range(9)}
        slope, aspect = calculate_terrain_slope(elevations)
        assert isinstance(slope, (int, float))
        assert isinstance(aspect, (int, float))

    def test_calculate_flow_direction(self):
        elevations = {
            0: 100, 1: 101, 2: 102,
            3: 97, 4: 98, 5: 99,
            6: 94, 7: 95, 8: 96,
        }
        direction = calculate_flow_direction(elevations)
        assert direction in [-1, 0, 1, 2, 3, 4, 5, 6, 7]

    def test_calculate_flow_direction_flat(self):
        elevations = {i: 100 for i in range(9)}
        direction = calculate_flow_direction(elevations)
        assert direction == -1

    def test_calculate_flow_accumulation(self):
        dem_grid = {
            (0.0, 0.0): 100, (0.0, 0.001): 99, (0.0, 0.002): 98,
            (0.001, 0.0): 97, (0.001, 0.001): 96, (0.001, 0.002): 95,
            (0.002, 0.0): 94, (0.002, 0.001): 93, (0.002, 0.002): 92,
        }
        acc = calculate_flow_accumulation(dem_grid)
        assert len(acc) == 9
        assert all(isinstance(v, int) for v in acc.values())

    def test_detect_terrain_depressions(self):
        dem_grid = {
            (0.0, 0.0): 90, (0.0, 0.001): 100, (0.0, 0.002): 100,
            (0.001, 0.0): 100, (0.001, 0.001): 95, (0.001, 0.002): 100,
            (0.002, 0.0): 100, (0.002, 0.001): 100, (0.002, 0.002): 100,
        }
        depressions = detect_terrain_depressions(dem_grid)
        assert len(depressions) >= 1

    def test_estimate_flood_depth(self):
        depth = estimate_flood_depth(None, upstream_volume_m3=5000, cell_area_m2=1000)
        assert depth == 5.0

    def test_estimate_flood_velocity(self):
        velocity = estimate_flood_velocity(1.0, slope_rad=0.01)
        assert velocity > 0

    def test_simulate_river_overflow(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='River Overflow Test',
            creation_source='river_discharge',
            geometry=polygon,
            risk_score=0.5,
            state='active',
        )
        updated, params = simulate_river_overflow(zone, discharge_m3s=100, bankfull_capacity_m3s=50)
        assert params['overflow'] is True
        assert params['depth_m'] > 0


class TestHydrologicalPropagation:
    def test_propagate_with_hydrology(self):
        polygon = Polygon.from_bbox((36.8, -1.3, 36.9, -1.2))
        zone = DynamicZone.objects.create(
            name='Hydro Propagation Zone',
            creation_source='weather',
            geometry=polygon,
            risk_score=0.7,
            confidence=0.8,
            state='active',
        )
        cell = H3Cell.objects.create(
            h3_index='8921c1b63fffffff',
            resolution=7,
            centroid_lat=-1.2921,
            centroid_lon=36.8219,
            current_risk_score=0.7,
        )
        zone.h3_cells.add(cell)

        with patch('core.zoning.propagation.fetch_dem_tile_batch', return_value={
            (-1.2921, 36.8219): 1000,
            (-1.2931, 36.8219): 1005,
            (-1.2931, 36.8229): 1003,
            (-1.2921, 36.8229): 1002,
            (-1.2911, 36.8219): 998,
            (-1.2911, 36.8229): 999,
            (-1.2911, 36.8209): 997,
            (-1.2921, 36.8209): 995,
            (-1.2931, 36.8209): 1001,
        }):
            propagation = propagate_flood(zone, forecast_hours=6)
            assert propagation is not None
            assert propagation.forecast_hours == 6
            assert propagation.predicted_risk_score >= 0.0
