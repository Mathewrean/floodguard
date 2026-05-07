import pytest
import responses
from django.contrib.gis.geos import Point
from core.models import FloodReading, AlertLog
from tests.factories import AlertZoneFactory, UserFactory
from core.tasks import fetch_flood_api, run_risk_scoring, dispatch_alerts


@pytest.mark.django_db
class TestFetchFloodAPITask:
    @responses.activate
    def test_creates_flood_reading_records(self):
        # Mock Open-Meteo API
        responses.add(
            responses.GET,
            'https://api.open-meteo.com/v1/forecast',
            json={
                'hourly': {
                    'time': ['2023-01-01T12:00'],
                    'river_discharge': [100.0]
                }
            },
            status=200
        )
        zone = AlertZoneFactory()
        fetch_flood_api(zone.id)
        assert FloodReading.objects.filter(source='open_meteo').exists()


@pytest.mark.django_db
class TestRunRiskScoringTask:
    def test_loads_model_and_writes_risk_score(self, mocker):
        # Mock ML model
        mock_model = mocker.MagicMock()
        mock_model.predict.return_value = [0.8]
        mocker.patch('joblib.load', return_value=mock_model)
        reading = FloodReading.objects.create(
            location=Point(36.8, -1.3, srid=4326),
            water_level_metres=5.0,
            source='test'
        )
        run_risk_scoring(reading.id)
        reading.refresh_from_db()
        assert reading.risk_score == 0.8


@pytest.mark.django_db
class TestDispatchAlertsTask:
    def test_writes_alert_log(self, mocker):
        # Mock SMS API
        mocker.patch('requests.post')
        zone = AlertZoneFactory()
        user = UserFactory()
        # Assume users in zone
        dispatch_alerts(zone.id, 0.8)
        assert AlertLog.objects.filter(alert_zone=zone).exists()


@pytest.mark.django_db
class TestAlertDeduplication:
    def test_first_alert_sends_second_does_not(self, mocker):
        mock_sms = mocker.patch('requests.post')
        zone = AlertZoneFactory()
        user = UserFactory()
        # First dispatch
        dispatch_alerts(zone.id, 0.8)
        assert mock_sms.call_count == 1
        # Second within 3 hours
        dispatch_alerts(zone.id, 0.8)
        assert mock_sms.call_count == 1  # Still 1