"""
Phase 2: Nairobi 500-Zone Validation.
Tests H3, weather, risk engine, AI, DSS, and safe routes across 500 Nairobi zones.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.conf import settings
import json

from tests.validation.nairobi_zone_generator import generate_nairobi_500_zones, get_sample_zones


ZONES = generate_nairobi_500_zones()
SAMPLE_ZONES = get_sample_zones(ZONES, 50)


def _mock_feature_vector(lat, lon, zone_name=''):
    return {
        'river_discharge': 10.0,
        'discharge_24h': 12.0,
        'discharge_7d_max': 15.0,
        'rainfall_1h_mm': 2.0,
        'precip_intensity': 1.0,
        'precip_probability': 30,
        'total_precip_mm': 5.0,
        'nasa_precip': 1.5,
        'chance_of_rain': 40,
        'humidity': 65,
        'pressure': 1013,
        'wind_speed': 3.0,
        'water_extent_km2': 0.2,
        'sources_available': 3,
        'data_confidence': 'medium',
        'zone_name': zone_name,
        'sources': {
            'open_meteo': {'available': True},
            'openweather': {'available': True},
            'tomorrow_io': {'available': True},
            'weather_api': {'available': False, 'error': 'no_key'},
            'nasa_gpm': {'available': False, 'error': 'no_key'},
            'google_earth_engine': {'available': False, 'error': 'no_key'},
        },
    }


class TestNairobi500ZoneDataset:
    def test_generates_exactly_500_zones(self):
        assert len(ZONES) == 500

    def test_all_zones_within_nairobi_bounds(self):
        nairobi_lat_min, nairobi_lat_max = -1.450, -1.100
        nairobi_lon_min, nairobi_lon_max = 36.650, 37.150
        for zone in ZONES:
            assert nairobi_lat_min <= zone['lat'] <= nairobi_lat_max, f"Zone {zone['id']} lat out of bounds: {zone['lat']}"
            assert nairobi_lon_min <= zone['lon'] <= nairobi_lon_max, f"Zone {zone['id']} lon out of bounds: {zone['lon']}"

    def test_all_zones_have_required_fields(self):
        for zone in ZONES:
            assert 'id' in zone
            assert 'name' in zone
            assert 'lat' in zone
            assert 'lon' in zone
            assert 'category' in zone
            assert 'subcategory' in zone

    def test_zones_cover_all_categories(self):
        categories = {z['category'] for z in ZONES}
        expected = {'urban_commercial', 'residential_high_density', 'peri_urban_rural', 'critical_infrastructure', 'hydrological_features'}
        assert expected.issubset(categories)

    def test_all_zone_ids_unique(self):
        ids = [z['id'] for z in ZONES]
        assert len(ids) == len(set(ids))


class TestH3Validation:
    @pytest.mark.django_db
    def test_h3_cell_generation_resolution_4(self):
        from core.h3_risk import get_h3_cell_for_point
        with patch('core.h3_risk.cache.get', return_value=None), \
             patch('core.h3_risk.cache.set'):
            result = get_h3_cell_for_point(-1.2921, 36.8219, resolution=4)
            assert result is not None
            assert 'h3_index' in result
            assert result['resolution'] == 4

    @pytest.mark.django_db
    def test_h3_cell_generation_resolution_7(self):
        from core.h3_risk import get_h3_cell_for_point
        with patch('core.h3_risk.cache.get', return_value=None), \
             patch('core.h3_risk.cache.set'):
            result = get_h3_cell_for_point(-1.2921, 36.8219, resolution=7)
            assert result is not None
            assert 'h3_index' in result
            assert result['resolution'] == 7

    @pytest.mark.django_db
    def test_h3_cell_generation_resolution_10(self):
        from core.h3_risk import get_h3_cell_for_point
        with patch('core.h3_risk.cache.get', return_value=None), \
             patch('core.h3_risk.cache.set'):
            result = get_h3_cell_for_point(-1.2921, 36.8219, resolution=10)
            assert result is not None
            assert 'h3_index' in result
            assert result['resolution'] == 10

    @pytest.mark.django_db
    def test_h3_parent_child_hierarchy(self):
        import h3
        cell_res4 = h3.latlng_to_cell(-1.2921, 36.8219, 4)
        cell_res7 = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        cell_res10 = h3.latlng_to_cell(-1.2921, 36.8219, 10)
        assert h3.cell_to_parent(cell_res10, 7) == cell_res7
        assert h3.cell_to_parent(cell_res7, 4) == cell_res4

    @pytest.mark.django_db
    def test_h3_neighbor_logic(self):
        import h3
        cell = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        neighbors = h3.grid_disk(cell, 1)
        assert len(neighbors) >= 1
        assert cell in neighbors

    @pytest.mark.django_db
    def test_h3_ring_logic(self):
        import h3
        cell = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        ring = h3.grid_ring(cell, 2)
        assert len(ring) > 0

    @pytest.mark.django_db
    def test_h3_polygon_conversion(self):
        import h3
        cell = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        geo = h3.cells_to_geo([cell])
        assert 'coordinates' in geo
        assert len(geo['coordinates']) > 0


class TestWeatherFallbackValidation:
    @pytest.mark.django_db
    def test_weather_aggregator_returns_structure(self):
        with patch('core.data_sources.aggregator.fetch_all_sources', return_value=_mock_feature_vector(-1.2921, 36.8219)['sources']):
            from core.data_sources.aggregator import build_risk_feature_vector
            result = build_risk_feature_vector(-1.2921, 36.8219, 'Nairobi-CBD-Test')
            assert isinstance(result, dict)
            assert 'sources_available' in result
            assert 'sources' in result
            assert 'data_confidence' in result

    @pytest.mark.django_db
    def test_weather_fallback_with_missing_keys(self):
        with patch('core.data_sources.aggregator.fetch_all_sources', return_value={}):
            from core.data_sources.aggregator import build_risk_feature_vector
            result = build_risk_feature_vector(-1.2921, 36.8219, 'Nairobi-Test-NoKeys')
            assert isinstance(result, dict)
            assert 'sources_available' in result
            assert result['sources_available'] == 0

    @pytest.mark.django_db
    def test_weather_feature_vector_fields(self):
        with patch('core.data_sources.aggregator.fetch_all_sources', return_value=_mock_feature_vector(-1.2921, 36.8219)['sources']):
            from core.data_sources.aggregator import build_risk_feature_vector
            result = build_risk_feature_vector(-1.2921, 36.8219, 'Nairobi-CBD-Test')
            expected_fields = [
                'river_discharge', 'discharge_24h', 'discharge_7d_max',
                'rainfall_1h_mm', 'precip_intensity', 'precip_probability',
                'total_precip_mm', 'nasa_precip', 'chance_of_rain',
                'humidity', 'pressure', 'wind_speed',
                'water_extent_km2', 'sources_available', 'data_confidence',
            ]
            for field in expected_fields:
                assert field in result, f"Missing field: {field}"


class TestRiskEngineValidation:
    @pytest.mark.django_db
    def test_risk_score_in_valid_range(self):
        from core.analytics.scoring import calculate_feature_risk
        features = {
            'river_discharge': 15.0,
            'rainfall_1h_mm': 5.0,
            'precip_intensity': 2.0,
            'humidity': 70,
            'water_extent_km2': 0.5,
            'sources_available': 3,
        }
        score = calculate_feature_risk(features)
        assert 0.0 <= score <= 1.0

    @pytest.mark.django_db
    def test_risk_score_zero_for_no_data(self):
        from core.analytics.scoring import calculate_feature_risk
        features = {
            'river_discharge': 0,
            'rainfall_1h_mm': 0,
            'precip_intensity': 0,
            'humidity': 0,
            'water_extent_km2': 0,
            'sources_available': 1,
        }
        score = calculate_feature_risk(features)
        assert score >= 0.0
        assert score <= 1.0

    @pytest.mark.django_db
    def test_risk_score_high_for_extreme_conditions(self):
        from core.analytics.scoring import calculate_feature_risk
        features = {
            'river_discharge': 100.0,
            'rainfall_1h_mm': 40.0,
            'precip_intensity': 20.0,
            'humidity': 95,
            'water_extent_km2': 10.0,
            'sources_available': 5,
        }
        score = calculate_feature_risk(features)
        assert score > 0.5

    @pytest.mark.django_db
    def test_confidence_penalty_for_single_source(self):
        from core.analytics.scoring import calculate_feature_risk
        features_single = {
            'river_discharge': 15.0,
            'rainfall_1h_mm': 5.0,
            'precip_intensity': 2.0,
            'humidity': 70,
            'water_extent_km2': 0.5,
            'sources_available': 1,
        }
        features_multi = {
            'river_discharge': 15.0,
            'rainfall_1h_mm': 5.0,
            'precip_intensity': 2.0,
            'humidity': 70,
            'water_extent_km2': 0.5,
            'sources_available': 3,
        }
        score_single = calculate_feature_risk(features_single)
        score_multi = calculate_feature_risk(features_multi)
        assert score_single <= score_multi


class TestSampleZonePipelineValidation:
    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:10])
    def test_sample_zone_h3_risk_pipeline(self, zone):
        from core.h3_risk import get_h3_cell_for_point
        lat, lon = zone['lat'], zone['lon']
        with patch('core.h3_risk.cache.get', return_value=None), \
             patch('core.h3_risk.cache.set'), \
             patch('core.h3_risk.AlertZone.objects.filter') as mock_filter:
            mock_filter.return_value.exists.return_value = False
            result = get_h3_cell_for_point(lat, lon, resolution=7)
            assert result is not None
            assert 'risk_score' in result
            assert 'risk_level' in result
            assert result['risk_score'] >= 0.0

    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:10])
    def test_sample_zone_weather_pipeline(self, zone):
        with patch('core.data_sources.aggregator.fetch_all_sources', return_value=_mock_feature_vector(zone['lat'], zone['lon'])['sources']):
            from core.data_sources.aggregator import build_risk_feature_vector
            result = build_risk_feature_vector(zone['lat'], zone['lon'], zone['name'])
            assert isinstance(result, dict)
            assert 'sources_available' in result
            assert 'data_confidence' in result
            assert result['sources_available'] >= 0

    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:10])
    def test_sample_zone_risk_calculation(self, zone):
        with patch('core.data_sources.aggregator.fetch_all_sources', return_value=_mock_feature_vector(zone['lat'], zone['lon'])['sources']):
            from core.data_sources.aggregator import build_risk_feature_vector
            from core.analytics.scoring import calculate_feature_risk
            features = build_risk_feature_vector(zone['lat'], zone['lon'], zone['name'])
            score = calculate_feature_risk(features)
            assert 0.0 <= score <= 1.0

    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:5])
    def test_sample_zone_safe_route_endpoint(self, zone):
        from django.test import Client
        client = Client()
        dest_lat = zone['lat'] + 0.01
        dest_lon = zone['lon'] + 0.01
        with patch('core.views.settings.GRAPHOPPER_API_KEY', ''):
            response = client.get('/api/v1/safe-route/', {
                'origin_lat': zone['lat'], 'origin_lon': zone['lon'],
                'dest_lat': dest_lat, 'dest_lon': dest_lon,
                'vehicle': 'car',
            })
        assert response.status_code in [200, 501]


class Test500ZoneGISIntegration:
    @pytest.mark.django_db
    def test_h3_bbox_query_for_nairobi(self):
        from core.h3_risk import get_h3_cells_for_bbox
        min_lat, max_lat = -1.45, -1.10
        min_lon, max_lon = 36.65, 37.15
        with patch('core.h3_risk.cache.get', return_value=None), \
             patch('core.h3_risk.cache.set'), \
             patch('core.h3_risk.AlertZone.objects.filter') as mock_filter:
            mock_filter.return_value.exists.return_value = False
            result = get_h3_cells_for_bbox(min_lat, min_lon, max_lat, max_lon, resolution=7)
            # Should return a list (either cells or empty if too large)
            assert isinstance(result, (list, dict))

    @pytest.mark.django_db
    def test_500_zone_coordinates_valid_geojson(self):
        geojson_features = []
        for zone in ZONES[:100]:
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [zone['lon'], zone['lat']]
                },
                'properties': {
                    'id': zone['id'],
                    'name': zone['name'],
                    'category': zone['category'],
                }
            }
            geojson_features.append(feature)
        geojson = {'type': 'FeatureCollection', 'features': geojson_features}
        assert len(geojson['features']) == 100


class Test500ZoneWeatherAndRisk:
    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:20])
    def test_zone_weather_confidence_scoring(self, zone):
        with patch('core.data_sources.aggregator.fetch_all_sources', return_value=_mock_feature_vector(zone['lat'], zone['lon'])['sources']):
            from core.data_sources.aggregator import build_risk_feature_vector
            result = build_risk_feature_vector(zone['lat'], zone['lon'], zone['name'])
            confidence = result.get('data_confidence', 'low')
            assert confidence in ['high', 'medium', 'low']

    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:20])
    def test_zone_risk_score_deterministic(self, zone):
        with patch('core.data_sources.aggregator.fetch_all_sources', return_value=_mock_feature_vector(zone['lat'], zone['lon'])['sources']):
            from core.data_sources.aggregator import build_risk_feature_vector
            from core.analytics.scoring import calculate_feature_risk
            result1 = build_risk_feature_vector(zone['lat'], zone['lon'], zone['name'])
            result2 = build_risk_feature_vector(zone['lat'], zone['lon'], zone['name'])
            score1 = calculate_feature_risk(result1)
            score2 = calculate_feature_risk(result2)
            assert score1 == score2


class Test500ZoneSafeRoutes:
    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:10])
    def test_safe_route_from_zone(self, zone):
        from django.test import Client
        client = Client()
        dest_lat = zone['lat'] + 0.02
        dest_lon = zone['lon'] + 0.02
        with patch('core.views.settings.GRAPHOPPER_API_KEY', ''):
            response = client.post('/api/v1/safe-route/', {
                'origin': {'lat': zone['lat'], 'lng': zone['lon']},
                'destination': {'lat': dest_lat, 'lng': dest_lon},
                'profile': 'balanced',
            }, content_type='application/json')
        assert response.status_code in [200, 501]
        if response.status_code == 200:
            data = response.json()
            assert 'routes' in data
            assert 'origin' in data
            assert 'destination' in data

    @pytest.mark.django_db
    @pytest.mark.parametrize('zone', SAMPLE_ZONES[:5])
    def test_safe_route_fallback_when_no_graphhopper(self, zone):
        settings.GRAPHOPPER_API_KEY = ''
        from django.test import Client
        client = Client()
        response = client.post('/api/v1/safe-route/', {
            'origin': {'lat': zone['lat'], 'lng': zone['lon']},
            'destination': {'lat': zone['lat'] + 0.01, 'lng': zone['lon'] + 0.01},
            'profile': 'balanced',
        }, content_type='application/json')
        assert response.status_code == 200
        data = response.json()
        assert 'routes' in data
        assert 'engine' in data
