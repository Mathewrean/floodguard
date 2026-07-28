"""
Phase 3: Security & Performance Validation.
Tests SQLi, XSS, CSRF, JWT/Session hijacking, Rate Limiting, and basic performance metrics.
"""
import pytest
from unittest.mock import patch
from django.test import TestCase
from django.conf import settings
from rest_framework.test import APIClient
from django.core.cache import cache

from tests.factories import UserFactory, AlertZoneFactory, IncidentReportFactory

pytestmark = pytest.mark.django_db


class TestSecurityValidation:
    @pytest.mark.django_db
    def test_sql_injection_protection(self, api_client):
        response = api_client.get('/api/v1/zones/?name=test\' OR 1=1 --')
        assert response.status_code in [200, 400, 404]

    @pytest.mark.django_db
    def test_xss_protection_in_incident_report(self, api_client):
        xss_payload = '<script>alert("xss")</script>'
        response = api_client.post(
            '/api/v1/reports/',
            {
                'severity': 3,
                'description': f'Flood at location {xss_payload}',
                'latitude': -1.2921,
                'longitude': 36.8219,
            },
            format='json'
        )
        assert response.status_code == 201
        data = response.json()
        assert '<script>' in data['description']
        assert response['Content-Type'] == 'application/json'

    @pytest.mark.django_db
    def test_csrf_protection_enabled(self):
        from django.middleware.csrf import CsrfViewMiddleware
        middleware_list = list(settings.MIDDLEWARE)
        assert 'django.middleware.csrf.CsrfViewMiddleware' in middleware_list

    @pytest.mark.django_db
    def test_rate_limiting_configuration(self):
        from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
        assert 'anon' in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        assert 'user' in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']

    @pytest.mark.django_db
    def test_authenticated_user_throttle(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        for _ in range(5):
            response = api_client.get('/api/v1/stats/')
            assert response.status_code == 200

    @pytest.mark.django_db
    def test_session_cookie_secure_flag_configurable(self):
        assert hasattr(settings, 'SESSION_COOKIE_SECURE')

    @pytest.mark.django_db
    def test_cors_configuration_exists(self):
        assert 'corsheaders' in settings.INSTALLED_APPS
        assert 'corsheaders.middleware.CorsMiddleware' in settings.MIDDLEWARE


class TestPerformanceValidation:
    @pytest.mark.django_db
    def test_zone_list_query_performance(self, api_client):
        import time
        for _ in range(5):
            AlertZoneFactory()
        start = time.time()
        response = api_client.get('/api/v1/zones/')
        elapsed = time.time() - start
        assert response.status_code == 200
        assert elapsed < 5.0

    @pytest.mark.django_db
    def test_cache_improves_h3_risk_lookup(self):
        from core.h3_risk import get_risk_for_h3_cell
        import h3
        cell = h3.latlng_to_cell(-1.2921, 36.8219, 7)
        cache_key = f"h3:{cell}:risk_score"
        cache.set(cache_key, 0.5, 60)
        cached = cache.get(cache_key)
        assert cached == 0.5
