import pytest
from django.urls import reverse
from django.contrib.gis.geos import Point
from rest_framework import status
from rest_framework.test import APIClient
from core.models import IncidentReport
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
        assert 'type' in response.data[0]['polygon']  # GeoJSON


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