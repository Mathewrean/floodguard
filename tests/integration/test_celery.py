import pytest
import responses
from django.contrib.gis.geos import Point
from core.models import FloodReading, AlertLog, UserProfile
from tests.factories import AlertZoneFactory, UserFactory, AuthorityUserFactory
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
        # Mock Open-Meteo API
        mock_requests = mocker.patch('requests.get')
        class MockResp:
            def raise_for_status(self): pass
            def json(self):
                return {
                    'hourly': {
                        'time': ['2023-01-01T12:00'],
                        'river_discharge': [5.0]
                    }
                }
        mock_requests.return_value = MockResp()
        # Create a zone that contains the reading location
        from django.contrib.gis.geos import Polygon
        zone = AlertZoneFactory(
            polygon=Polygon([(36.7, -1.4), (36.9, -1.4), (36.9, -1.2), (36.7, -1.2), (36.7, -1.4)], srid=4326)
        )
        # Create multiple readings for high confidence
        for i in range(12):
            FloodReading.objects.create(
                location=Point(36.8, -1.3, srid=4326),
                water_level_metres=5.0,
                source='test'
            )
        reading = FloodReading.objects.filter(location__within=zone.polygon).first()
        run_risk_scoring(reading.id)
        reading.refresh_from_db()
        assert reading.risk_score == 0.8


@pytest.mark.django_db
class TestDispatchAlertsTask:
    def test_writes_alert_log(self, mocker):
        # Mock SMS API
        mock_post = mocker.patch('requests.post')
        class MockResp:
            def raise_for_status(self): pass
            def json(self):
                return {'SMSMessageData': {'Recipients': [{'messageId': 'msg_123'}]}}
        mock_post.return_value = MockResp()
        from django.contrib.gis.geos import Polygon
        zone = AlertZoneFactory(
            risk_threshold=0.5,
            polygon=Polygon([(36.7, -1.4), (36.9, -1.4), (36.9, -1.2), (36.7, -1.2), (36.7, -1.4)], srid=4326)
        )
        # Authority user needed for dispatch; ensure profile has phone
        authority = AuthorityUserFactory()
        profile, _ = UserProfile.objects.get_or_create(user=authority)
        profile.phone_number = '+254712345678'
        profile.save()
        # Manually call dispatch_alerts
        dispatch_alerts(zone.id, 0.8)
        assert AlertLog.objects.filter(alert_zone=zone).exists()


@pytest.mark.django_db
class TestAlertDeduplication:
    def setup_method(self):
        # Clear Redis before each test to avoid interference
        from core.tasks import redis_client
        redis_client.flushdb()

    def test_first_alert_sends_second_does_not(self, mocker):
        mock_sms = mocker.patch('requests.post')
        class MockResp:
            def raise_for_status(self): pass
            def json(self):
                return {'SMSMessageData': {'Recipients': [{'messageId': 'msg_123'}]}}
        mock_sms.return_value = MockResp()
        from django.contrib.gis.geos import Polygon
        zone = AlertZoneFactory(
            risk_threshold=0.5,
            polygon=Polygon([(36.7, -1.4), (36.9, -1.4), (36.9, -1.2), (36.7, -1.2), (36.7, -1.4)], srid=4326)
        )
        # Authority user needed for dispatch; ensure phone
        authority = AuthorityUserFactory()
        profile, _ = UserProfile.objects.get_or_create(user=authority)
        profile.phone_number = '+254712345678'
        profile.save()
        # First dispatch
        dispatch_alerts(zone.id, 0.8)
        assert mock_sms.call_count == 1
        # Second within 3 hours
        dispatch_alerts(zone.id, 0.8)
        assert mock_sms.call_count == 1  # Still 1 due to deduplication