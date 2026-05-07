import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from core.models import AlertZone, UserProfile
from tests.factories import AlertZoneFactory, UserFactory, AuthorityUserFactory
from rest_framework.test import APIRequestFactory, force_authenticate


@pytest.mark.django_db
class TestManualAlertOverride:
    def setup_method(self):
        self.zone = AlertZoneFactory(risk_threshold=0.5)
        self.authority_user = AuthorityUserFactory()
        self.admin_user = UserFactory(is_superuser=True)
        self.citizen_user = UserFactory()

    def test_manual_override_fields_exist(self):
        """Test that manual override fields exist on AlertZone model"""
        assert hasattr(self.zone, 'manual_override_active')
        assert hasattr(self.zone, 'manual_override_until')
        assert self.zone.manual_override_active is False
        assert self.zone.manual_override_until is None

    def test_is_override_active_property_false_by_default(self):
        """Test that is_override_active returns False by default"""
        assert self.zone.is_override_active is False

    def test_is_override_active_property_true_when_active(self):
        """Test that is_override_active returns True when override is active"""
        self.zone.manual_override_active = True
        self.zone.save()
        assert self.zone.is_override_active is True

    def test_is_override_active_property_false_when_expired(self):
        """Test that is_override_active returns False when override has expired"""
        self.zone.manual_override_active = True
        self.zone.manual_override_until = timezone.now() - timedelta(hours=1)
        self.zone.save()
        # After save, the override should be deactivated due to expiration
        self.zone.refresh_from_db()
        assert self.zone.manual_override_active is False
        assert self.zone.manual_override_until is None
        assert self.zone.is_override_active is False

    def test_manual_override_api_endpoint_exists(self):
        """Test that the manual override API endpoint exists"""
        # This test will pass if the endpoint is properly registered
        # We're checking that our viewset has the manual_override action
        from core.views import AlertZoneViewSet
        assert hasattr(AlertZoneViewSet, 'manual_override')

    def test_only_authority_and_admin_can_set_manual_override(self):
        """Test that only authority and admin users can set manual override"""
        from core.views import AlertZoneViewSet
        from rest_framework.test import APIRequestFactory, force_authenticate
        
        factory = APIRequestFactory()
        view = AlertZoneViewSet.as_view({'post': 'manual_override'})
        
        # Test with citizen user (should fail)
        request = factory.post(f'/api/v1/alertzones/{self.zone.id}/manual_override/', 
                              {'active': True}, format='json')
        force_authenticate(request, user=self.citizen_user)
        response = view(request, pk=self.zone.id)
        assert response.status_code == 403  # Permission denied
        
        # Test with authority user (should succeed)
        request = factory.post(f'/api/v1/alertzones/{self.zone.id}/manual_override/', 
                              {'active': True, 'duration_hours': 2}, format='json')
        force_authenticate(request, user=self.authority_user)
        response = view(request, pk=self.zone.id)
        assert response.status_code == 200
        assert response.data['manual_override_active'] is True
        
        # Test with admin user (should succeed)
        request = factory.post(f'/api/v1/alertzones/{self.zone.id}/manual_override/', 
                              {'active': True}, format='json')
        force_authenticate(request, user=self.admin_user)
        response = view(request, pk=self.zone.id)
        assert response.status_code == 200
        assert response.data['manual_override_active'] is True

    def test_manual_override_can_be_deactivated(self):
        """Test that manual override can be turned off"""
        from core.views import AlertZoneViewSet
        from rest_framework.test import APIRequestFactory, force_authenticate
        
        factory = APIRequestFactory()
        view = AlertZoneViewSet.as_view({'post': 'manual_override'})
        
        # First activate override
        request = factory.post(f'/api/v1/alertzones/{self.zone.id}/manual_override/', 
                              {'active': True, 'duration_hours': 2}, format='json')
        force_authenticate(request, user=self.authority_user)
        response = view(request, pk=self.zone.id)
        assert response.status_code == 200
        assert response.data['manual_override_active'] is True
        
        # Then deactivate it
        request = factory.post(f'/api/v1/alertzones/{self.zone.id}/manual_override/', 
                              {'active': False}, format='json')
        force_authenticate(request, user=self.authority_user)
        response = view(request, pk=self.zone.id)
        assert response.status_code == 200
        assert response.data['manual_override_active'] is False
        assert response.data['manual_override_until'] is None

    def test_manual_override_with_duration_sets_until_field(self):
        """Test that setting override with duration sets the until field correctly"""
        from core.views import AlertZoneViewSet
        from rest_framework.test import APIRequestFactory, force_authenticate
        
        factory = APIRequestFactory()
        view = AlertZoneViewSet.as_view({'post': 'manual_override'})
        
        request = factory.post(f'/api/v1/alertzones/{self.zone.id}/manual_override/', 
                              {'active': True, 'duration_hours': 3}, format='json')
        force_authenticate(request, user=self.authority_user)
        response = view(request, pk=self.zone.id)
        assert response.status_code == 200
        assert response.data['manual_override_active'] is True
        assert response.data['manual_override_until'] is not None
        
        # Verify the until field is set correctly (approximately 3 hours from now)
        until = timezone.datetime.fromisoformat(response.data['manual_override_until'].replace('Z', '+00:00'))
        expected_until = timezone.now() + timedelta(hours=3)
        # Allow a small time difference due to processing
        assert abs((until - expected_until).total_seconds()) < 5

    def test_dispatch_alerts_respects_manual_override(self):
        """Test that dispatch_alerts task respects manual override"""
        from core.tasks import dispatch_alerts
        from unittest.mock import patch
        
        # Activate manual override
        self.zone.manual_override_active = True
        self.zone.save()
        
        # Mock the build_alert_message function to avoid actual alert building
        with patch('core.alerts.messages.build_alert_message') as mock_build:
            mock_build.return_value = ("Test message", "high")
            
            # Call dispatch_alerts - should not proceed due to override
            dispatch_alerts(self.zone.id, 0.8)
            
            # Verify that build_alert_message was not called (early return)
            mock_build.assert_not_called()