"""
Tests for GPS Location Engine and Universal Search.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import timedelta

from django.contrib.gis.geos import Point, Polygon
from django.utils import timezone

from core.models import AlertZone, DynamicZone, AdministrativeBoundary, User, UserProfile
from core.zoning.location_engine import process_user_location, LocationEngine, check_geofence_entry
from core.zoning.search_engine import universal_search

pytestmark = pytest.mark.django_db


class TestLocationEngine:
    def test_process_user_location_basic(self):
        user = User.objects.create_user(username='loc_user', password='test')
        result = process_user_location(user, -1.2921, 36.8219)
        assert result['user_id'] == user.id
        assert result['coordinates']['lat'] == -1.2921
        assert result['coordinates']['lon'] == 36.8219
        assert 'h3_cell' in result

    def test_location_engine_class(self):
        user = User.objects.create_user(username='loc_engine_user', password='test')
        engine = LocationEngine(user)
        location = engine.update_location(-1.2921, 36.8219, accuracy_m=10, source='gps')
        assert location['lat'] == -1.2921
        assert location['source'] == 'gps'
        assert engine.get_current_location() == location

    def test_geofence_entry_alert(self):
        user = User.objects.create_user(username='geo_user', password='test')
        polygon = Polygon.from_bbox((36.8, -1.3, 36.85, -1.25))
        zone = AlertZone.objects.create(
            name='High Risk Zone',
            polygon=polygon,
            risk_score=0.8,
            risk_threshold=0.65,
        )
        alerts = check_geofence_entry(user, -1.28, 36.82)
        assert len(alerts) >= 1
        assert any('geofence' in a['type'] for a in alerts)


class TestUniversalSearch:
    @patch('core.zoning.search_engine.cache.get', return_value=None)
    @patch('core.zoning.search_engine.cache.set')
    @patch('core.zoning.search_engine.AlertZone.objects.filter')
    @patch('core.zoning.search_engine.DynamicZone.objects.filter')
    @patch('core.zoning.search_engine.FloodReading.objects.filter')
    @patch('core.zoning.search_engine.AdministrativeBoundary.objects.filter')
    def test_search_coordinates(self, mock_admin, mock_reading, mock_dynamic, mock_alert, mock_cache_set, mock_cache_get):
        mock_alert.return_value.order_by.return_value.first.return_value = None
        mock_dynamic.return_value.order_by.return_value.first.return_value = None
        mock_reading.return_value.order_by.return_value.first.return_value = None
        mock_admin.return_value.first.return_value = None

        result = universal_search("-1.2921, 36.8219")
        assert result['type'] == 'coordinates'
        assert result['location'] is not None
        assert result['location']['lat'] == -1.2921

    @patch('core.zoning.search_engine.cache.get', return_value=None)
    @patch('core.zoning.search_engine.cache.set')
    @patch('core.zoning.search_engine.requests.get')
    def test_search_place_name(self, mock_get, mock_cache_set, mock_cache_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{
            'lat': '-1.2921', 'lon': '36.8219',
            'display_name': 'Nairobi, Kenya',
            'class': 'place',
            'importance': 0.8,
        }]
        mock_get.return_value = mock_resp

        result = universal_search("Nairobi")
        assert result['type'] == 'place_name'
        assert len(result['location']['results']) == 1

    def test_search_osm_feature(self):
        result = universal_search("hospital near Nairobi")
        assert result['type'] == 'osm_feature'
        assert result['location']['feature_type'] == 'hospital'

    @patch('core.zoning.search_engine.cache.get', return_value=None)
    @patch('core.zoning.search_engine.cache.set')
    @patch('core.zoning.search_engine.AlertZone.objects.filter')
    @patch('core.zoning.search_engine.DynamicZone.objects.filter')
    @patch('core.zoning.search_engine.FloodReading.objects.filter')
    @patch('core.zoning.search_engine.AdministrativeBoundary.objects.filter')
    def test_search_with_lat_lon(self, mock_admin, mock_reading, mock_dynamic, mock_alert, mock_cache_set, mock_cache_get):
        mock_alert.return_value.order_by.return_value.first.return_value = None
        mock_dynamic.return_value.order_by.return_value.first.return_value = None
        mock_reading.return_value.order_by.return_value.first.return_value = None
        mock_admin.return_value.first.return_value = None

        result = universal_search("test", lat=-1.2921, lon=36.8219)
        assert result['type'] == 'coordinates'
        assert result['location'] is not None
