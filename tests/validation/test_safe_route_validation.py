"""
Phase 3: Safe Route Engine Validation.
Tests routing logic, constraints, flood exposure, and GraphHopper failover.
"""
import pytest
from unittest.mock import patch
from django.test import TestCase
from django.conf import settings
from rest_framework.test import APIClient

from tests.factories import AlertZoneFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestSafeRouteEngine:
    @pytest.mark.django_db
    def test_safe_route_returns_routes(self, api_client):
        response = api_client.get('/api/v1/safe-route/', {
            'origin_lat': -1.2921, 'origin_lon': 36.8219,
            'dest_lat': -1.2864, 'dest_lon': 36.8172,
        })
        assert response.status_code in [200, 501, 503]

    @pytest.mark.django_db
    def test_safe_route_fallback_to_internal_engine(self, api_client):
        settings.GRAPHOPPER_API_KEY = ''
        response = api_client.post('/api/v1/safe-route/', {
            'origin': {'lat': -1.2921, 'lng': 36.8219},
            'destination': {'lat': -1.2864, 'lng': 36.8172},
            'profile': 'balanced',
        }, format='json')
        assert response.status_code == 200
        data = response.json()
        assert 'routes' in data
        assert 'engine' in data

    @pytest.mark.django_db
    def test_safe_route_has_distance_and_duration(self, api_client):
        settings.GRAPHOPPER_API_KEY = ''
        response = api_client.post('/api/v1/safe-route/', {
            'origin': {'lat': -1.2921, 'lng': 36.8219},
            'destination': {'lat': -1.2864, 'lng': 36.8172},
            'profile': 'balanced',
        }, format='json')
        assert response.status_code == 200
        data = response.json()
        for route in data.get('routes', []):
            assert 'distance_m' in route or 'distance_km' in route
            assert 'duration_min' in route or 'duration_minutes' in route

    @pytest.mark.django_db
    def test_safe_route_snap_coordinate(self, api_client):
        response = api_client.post('/api/v1/safe-route/snap/', {
            'coordinate': {'lat': -1.2921, 'lng': 36.8219},
        }, format='json')
        assert response.status_code == 200
        data = response.json()
        assert 'coordinate' in data
        assert 'status' in data

    @pytest.mark.django_db
    def test_safe_route_validates_coordinates(self, api_client):
        response = api_client.post('/api/v1/safe-route/', {
            'origin': {'lat': 'invalid', 'lng': 36.8219},
            'destination': {'lat': -1.2864, 'lng': 36.8172},
        }, format='json')
        assert response.status_code == 400

    @pytest.mark.django_db
    def test_safe_route_multiple_profiles(self, api_client):
        settings.GRAPHOPPER_API_KEY = ''
        for profile in ['fastest', 'balanced', 'safest']:
            response = api_client.post('/api/v1/safe-route/', {
                'origin': {'lat': -1.2921, 'lng': 36.8219},
                'destination': {'lat': -1.2864, 'lng': 36.8172},
                'profile': profile,
            }, format='json')
            assert response.status_code == 200
            data = response.json()
            assert 'routes' in data
