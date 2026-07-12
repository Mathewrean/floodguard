import json
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.contrib.gis.geos import Point
from rest_framework import status
from rest_framework.test import APIClient
from core.models import AlertZone, IncidentReport
from tests.factories import AlertZoneFactory, UserFactory, AuthorityUserFactory, IncidentReportFactory


@pytest.mark.django_db
class TestIncidentReportAPI:
    def setup_method(self):
        self.client = APIClient()

    def test_post_reports_201_with_valid_payload(self):
        url = reverse('incidentreport-list')
        data = {
            'location': {'type': 'Point', 'coordinates': [36.8, -1.3]},
            'severity': 3,
            'description': 'Flood reported'
        }
        response = self.client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert IncidentReport.objects.count() == 1

    def test_post_reports_400_with_out_of_bounds(self):
        url = reverse('incidentreport-list')
        data = {
            'location': {'type': 'Point', 'coordinates': [30.0, 0.0]},
            'severity': 3,
            'description': 'Flood reported'
        }
        response = self.client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_patch_verify_by_authority_200(self):
        authority = AuthorityUserFactory()
        self.client.force_authenticate(user=authority)
        report = IncidentReportFactory()
        url = reverse('incidentreport-verify', kwargs={'pk': report.pk})
        data = {'status': 'verified'}
        response = self.client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        report.refresh_from_db()
        assert report.status == 'verified'

    def test_patch_verify_by_citizen_403(self):
        citizen = UserFactory()
        self.client.force_authenticate(user=citizen)
        report = IncidentReportFactory()
        url = reverse('incidentreport-verify', kwargs={'pk': report.pk})
        data = {'status': 'verified'}
        response = self.client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAlertZoneAPI:
    def setup_method(self):
        self.client = APIClient()

    def test_get_zones_returns_geojson(self):
        AlertZoneFactory()
        url = reverse('alertzone-list')
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        # With pagination enabled, response.data is a paginated object with 'results' key
        zones = response.data.get('results', response.data)
        assert len(zones) > 0
        assert 'type' in zones[0]['polygon']  # GeoJSON


@pytest.mark.django_db
class TestPredictAPI:
    def setup_method(self):
        self.client = APIClient()
        authority = AuthorityUserFactory()
        self.client.force_authenticate(user=authority)

    def test_get_predict_returns_float(self):
        zone = AlertZoneFactory()
        url = reverse('floodreading-predict') + f'?zone_id={zone.id}&hours_ahead=8'
        # Assume endpoint exists
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data['risk_score'], float)


@pytest.mark.django_db
class TestDynamicZoneAPI:
    def setup_method(self):
        self.client = APIClient()

    def test_dynamic_zone_post_creates_zone_from_current_location(self, mocker):
        geo_payload = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {'address': {'suburb': 'Westlands'}}
        )
        mocker.patch('requests.get', return_value=geo_payload)
        mocker.patch(
            'core.views.build_risk_feature_vector',
            return_value={'sources_available': 3, 'data_confidence': 'high'},
        )
        mocker.patch('core.analytics.scoring.calculate_risk_score', return_value=0.72)

        response = self.client.post(
            reverse('dynamic-zone'),
            {'lat': -1.287, 'lon': 36.821, 'accuracy': 45},
            format='json',
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['has_zone'] is True
        assert response.data['created_zone'] is True
        assert response.data['zone_name'] == 'Dynamic Zone - Westlands'
        assert AlertZone.objects.count() == 1

    def test_dynamic_zone_get_is_read_only_live_assessment(self, mocker):
        mocker.patch('requests.get', side_effect=Exception('reverse geocoder unavailable'))
        mocker.patch(
            'core.views.build_risk_feature_vector',
            return_value={'sources_available': 1, 'data_confidence': 'low'},
        )
        mocker.patch('core.analytics.scoring.calculate_risk_score', return_value=0.25)

        response = self.client.get(reverse('dynamic-zone'), {'lat': -1.287, 'lon': 36.821})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['has_zone'] is False
        assert response.data['created_zone'] is False
        assert response.data['live_assessment'] is True
        assert AlertZone.objects.count() == 0


@pytest.mark.django_db
class TestRateLimiting:
    def setup_method(self):
        self.client = APIClient()

    def test_rate_limiter_429_after_10_submissions(self):
        url = reverse('incidentreport-list')
        data = {
            'location': {'type': 'Point', 'coordinates': [36.8, -1.3]},
            'severity': 3,
            'description': 'Flood reported'
        }
        for i in range(11):
            response = self.client.post(url, data, format='json', REMOTE_ADDR='192.168.1.1')
            if i < 10:
                assert response.status_code == status.HTTP_201_CREATED
            else:
                assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
class TestDataSourcesAPI:
    def setup_method(self):
        self.client = APIClient()

    def test_data_sources_requires_admin(self):
        user = UserFactory()
        self.client.force_authenticate(user=user)
        response = self.client.get(reverse('data-sources'))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_data_sources_admin_gets_sources_array(self, mocker):
        admin = UserFactory(is_staff=True, is_superuser=True)
        self.client.force_authenticate(user=admin)
        mocker.patch(
            'core.data_sources.aggregator.get_source_status',
            return_value=[
                {'name': 'open_meteo', 'configured': True, 'status': 'ok'},
                {'name': 'openweather', 'configured': False, 'status': 'no_key'},
            ],
        )

        response = self.client.get(reverse('data-sources'))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['sources']) == 2
        assert response.data['active_sources'] == 1
        assert response.data['data_confidence'] == 'low'


@pytest.mark.django_db
class TestAIFloodAnalysisAPI:
    def setup_method(self):
        self.client = APIClient()

    def test_ai_analysis_posts_live_source_payload_to_groq(self, mocker, settings):
        settings.GROQ_API_KEY = 'test-key'
        settings.OPENWEATHER_API_KEY = 'test-openweather-key'
        settings.TOMORROW_IO_API_KEY = 'test-tomorrow-key'
        settings.WEATHERAPI_KEY = 'test-weatherapi-key'
        settings.NASA_EARTHDATA_TOKEN = 'test-nasa-token'

        zone = AlertZoneFactory(risk_score=0.5)

        def fake_build_risk(lat, lon, zone_name=''):
            return {
                'river_discharge': 10,
                'rainfall_1h_mm': 2.5,
                'humidity': 70,
                'pressure': 1010,
                'wind_speed': 3,
                'sources_available': 4,
                'data_confidence': 'high',
                'zone_name': zone_name,
                'sources': {
                    'openweather': {'source': 'openweather', 'available': True, 'rainfall_1h_mm': 2.5},
                },
            }

        class FakeMessage:
            def __init__(self, content):
                self.content = content

        class FakeChoice:
            def __init__(self, message):
                self.message = message

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(model, messages, max_tokens, temperature):
                        return SimpleNamespace(choices=[FakeChoice(FakeMessage('{"overall_risk":"HIGH","summary":"Flood risk is elevated.","highest_risk_zone":"%s","immediate_actions":["Monitor river levels","Alert authorities"],"24h_outlook":"Rainfall likely to increase tonight.","safe_zones":["Zone A","Zone B"]}' % zone.name))])

        mocker.patch('core.views.build_risk_feature_vector', fake_build_risk)
        mocker.patch('core.views.Groq', lambda api_key: FakeClient())

        response = self.client.post(reverse('ai-analysis'))

        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['source'] == 'groq'
        assert response.data['analysis']['overall_risk'] == 'HIGH'
        assert response.data['analysis']['highest_risk_zone'] == zone.name
