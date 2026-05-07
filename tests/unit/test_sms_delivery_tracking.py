import pytest
from django.utils import timezone
from unittest.mock import patch
from core.models import AlertLog, AlertZone
from tests.factories import AlertZoneFactory


@pytest.mark.django_db
class TestSMSDeliveryReceiptTracking:
    def setup_method(self):
        self.zone = AlertZoneFactory(name="Test Zone")
        # Create an authority user to ensure dispatch has recipients
        from tests.factories import AuthorityUserFactory
        self.authority_user = AuthorityUserFactory()

    def test_alert_log_has_delivery_tracking_fields(self):
        """Test that AlertLog model has delivery tracking fields"""
        alert_log = AlertLog.objects.create(
            alert_zone=self.zone,
            message="Test message",
            channel="SMS"
        )
        
        # Check that delivery tracking fields exist
        assert hasattr(alert_log, 'delivery_status')
        assert hasattr(alert_log, 'provider_message_id')
        assert hasattr(alert_log, 'delivered_at')
        
        # Check default values
        assert alert_log.delivery_status == 'pending'
        assert alert_log.provider_message_id is None
        assert alert_log.delivered_at is None

    def test_alert_log_can_track_delivery_status(self):
        """Test that we can update and track delivery status"""
        alert_log = AlertLog.objects.create(
            alert_zone=self.zone,
            message="Test message",
            channel="SMS",
            delivery_status='pending'
        )
        
        # Update to sent
        alert_log.delivery_status = 'sent'
        alert_log.provider_message_id = 'msg_12345'
        alert_log.save()
        
        alert_log.refresh_from_db()
        assert alert_log.delivery_status == 'sent'
        assert alert_log.provider_message_id == 'msg_12345'
        
        # Update to delivered
        alert_log.delivery_status = 'delivered'
        alert_log.delivered_at = timezone.now()
        alert_log.save()
        
        alert_log.refresh_from_db()
        assert alert_log.delivery_status == 'delivered'
        assert alert_log.delivered_at is not None

    def test_alert_log_delivery_choices(self):
        """Test that delivery status choices are correct"""
        alert_log = AlertLog.objects.create(
            alert_zone=self.zone,
            message="Test message",
            channel="SMS"
        )
        
        # Test each valid choice
        valid_statuses = ['pending', 'sent', 'delivered', 'failed', 'undelivered']
        for status in valid_statuses:
            alert_log.delivery_status = status
            alert_log.save()
            alert_log.refresh_from_db()
            assert alert_log.delivery_status == status

    def test_dispatch_alerts_creates_tracked_alert_log(self):
        """Test that dispatch_alerts creates AlertLog with tracking fields"""
        from core.tasks import dispatch_alerts
        
        # Mock the build_alert_message function to avoid actual alert building
        with patch('core.alerts.messages.build_alert_message') as mock_build:
            mock_build.return_value = ("Test alert message", "high")
            
            # Call dispatch_alerts
            dispatch_alerts(self.zone.id, 0.8)
            
            # Check that an AlertLog was created with tracking fields
            alert_log = AlertLog.objects.first()
            assert alert_log is not None
            assert alert_log.alert_zone == self.zone
            assert alert_log.message == "Test alert message"
            assert alert_log.channel == 'SMS'
            assert alert_log.delivery_status == 'sent'  # Set by our implementation
            assert alert_log.provider_message_id is not None
            assert alert_log.provider_message_id.startswith('msg_')

    def test_dispatch_alerts_handles_failed_delivery(self):
        """Test that dispatch_alerts handles failed delivery correctly"""
        from core.tasks import dispatch_alerts
        
        # Mock the build_alert_message function
        with patch('core.alerts.messages.build_alert_message') as mock_build:
            mock_build.return_value = ("Test alert message", "high")
            
            # Mock an exception during SMS sending to simulate failure
            with patch('core.tasks.logger.info') as mock_info:
                mock_info.side_effect = Exception("Simulated SMS failure")
                
                # Call dispatch_alerts
                dispatch_alerts(self.zone.id, 0.8)
                
                # Check that an AlertLog was created with failed status
                alert_log = AlertLog.objects.first()
                assert alert_log is not None
                assert alert_log.delivery_status == 'failed'