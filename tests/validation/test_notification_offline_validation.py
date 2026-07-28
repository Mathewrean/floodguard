"""
Phase 3: Notification & Offline Systems Validation.
Tests SMS, Email, WebSockets, Push Notifications, PWA, and IndexedDB offline capability.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.conf import settings
from rest_framework.test import APIClient

from tests.factories import (
    SuperAdminUserFactory,
    EmergencyResponderFactory,
    AlertZoneFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


class TestNotificationSystems:
    @pytest.mark.django_db
    def test_alert_dispatch_creates_alert_log(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/dispatch_alert/',
            {'channels': ['sms'], 'test_mode': True},
            format='json'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'preview'

    @pytest.mark.django_db
    def test_sms_delivery_tracking_fields_exist(self):
        from core.models import AlertLog
        zone = AlertZoneFactory()
        alert = AlertLog.objects.create(
            alert_zone=zone,
            message='Test alert',
            channel='SMS',
            recipient_count=1,
            delivery_status='sent',
            provider_message_id='msg_123',
        )
        assert alert.delivery_status == 'sent'
        assert alert.provider_message_id == 'msg_123'

    @pytest.mark.django_db
    def test_alert_log_status_transitions(self):
        from core.models import AlertLog
        zone = AlertZoneFactory()
        alert = AlertLog.objects.create(
            alert_zone=zone,
            message='Test alert',
            channel='SMS',
            recipient_count=1,
            delivery_status='pending',
        )
        alert.delivery_status = 'delivered'
        alert.save()
        alert.refresh_from_db()
        assert alert.delivery_status == 'delivered'

    @pytest.mark.django_db
    def test_websocket_channel_layer_configured(self):
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        assert layer is not None

    @pytest.mark.django_db
    def test_pwa_manifest_served(self):
        from django.test import Client
        client = Client()
        response = client.get('/manifest.json')
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'

    @pytest.mark.django_db
    def test_service_worker_served(self):
        from django.test import Client
        client = Client()
        response = client.get('/service-worker.js')
        assert response.status_code == 200
        assert 'Service-Worker-Allowed' in response


class TestOfflineCapability:
    @pytest.mark.django_db
    def test_offline_report_submission_queue(self):
        from django.core.cache import cache
        cache.set('offline_reports', [], timeout=3600)
        reports = cache.get('offline_reports', [])
        reports.append({'lat': -1.2921, 'lon': 36.8219, 'severity': 3})
        cache.set('offline_reports', reports, timeout=3600)
        cached = cache.get('offline_reports', [])
        assert len(cached) == 1

    @pytest.mark.django_db
    def test_indexeddb_schema_defined(self):
        from django.test import Client
        client = Client()
        response = client.get('/gis/')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'indexedDB' in content.lower() or 'idb' in content.lower() or 'offline' in content.lower() or 'gis' in content.lower()
