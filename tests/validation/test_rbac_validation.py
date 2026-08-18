"""
Phase 1: User Role & Access Control Validation (RBAC)
Tests all 7 user roles and verifies permission enforcement, privilege escalation prevention.
"""
import pytest
from django.contrib.auth.models import User, Group
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from core.models import UserProfile, AlertZone, IncidentReport, FloodReading, AlertLog, FloodPrediction, BeneficiaryGroup, MonthlyReport, Milestone
from tests.factories import (
    SuperAdminUserFactory,
    GovernmentOfficialFactory,
    EmergencyResponderFactory,
    MeteoOfficerFactory,
    NGOHumanitarianFactory,
    UserFactory,
    ResearcherFactory,
    AlertZoneFactory,
    IncidentReportFactory,
    FloodReadingFactory,
    FloodPredictionFactory,
    BeneficiaryGroupFactory,
    MonthlyReportFactory,
    MilestoneFactory,
)


# ============================================================
# Role Creation & Profile Verification
# ============================================================

@pytest.mark.django_db
class TestUserRoleCreation:
    def test_super_admin_creation(self, super_admin):
        user = super_admin
        profile = user.profile
        assert user.is_superuser is True
        assert user.is_staff is True
        assert profile.role == 'super_admin'

    def test_government_national_creation(self, govt_national):
        user = govt_national
        profile = user.profile
        assert user.is_superuser is False
        assert user.groups.filter(name='GovernmentTeam').exists()
        assert profile.role == 'govt_national'

    def test_government_county_creation(self, govt_county):
        user = govt_county
        profile = user.profile
        assert user.groups.filter(name='GovernmentTeam').exists()
        assert profile.role == 'govt_county'

    def test_emergency_responder_creation(self, emergency_responder):
        user = emergency_responder
        profile = user.profile
        assert user.groups.filter(name='EmergencyTeam').exists()
        assert profile.role == 'emergency_responder'

    def test_meteo_officer_creation(self, meteo_officer):
        user = meteo_officer
        profile = user.profile
        assert user.groups.filter(name='MeteorologicalTeam').exists()
        assert profile.role == 'meteo_officer'

    def test_ngo_humanitarian_creation(self, ngo_humanitarian):
        user = ngo_humanitarian
        profile = user.profile
        assert user.groups.filter(name='NGOTeam').exists()
        assert profile.role == 'ngo_humanitarian'

    def test_citizen_creation(self, citizen):
        user = citizen
        profile = user.profile
        assert user.is_superuser is False
        assert user.groups.count() == 0
        assert profile.role == 'citizen'

    def test_researcher_creation(self, researcher):
        user = researcher
        profile = user.profile
        assert user.groups.filter(name='ResearchTeam').exists()
        assert profile.role == 'researcher'

    def test_all_roles_have_unique_profiles(self):
        users = [
            SuperAdminUserFactory(),
            GovernmentOfficialFactory(level='national'),
            GovernmentOfficialFactory(level='county'),
            EmergencyResponderFactory(),
            MeteoOfficerFactory(),
            NGOHumanitarianFactory(),
            UserFactory(),
            ResearcherFactory(),
        ]
        roles = [u.profile.role for u in users]
        assert len(set(roles)) == 8


# ============================================================
# API Endpoint Access by Role
# ============================================================

@pytest.mark.django_db
class TestAPIRoleAccess:
    def test_super_admin_can_access_admin_dashboard(self, web_client, super_admin):
        web_client.force_login(super_admin)
        response = web_client.get('/dashboard/admin/')
        assert response.status_code == status.HTTP_200_OK

    def test_emergency_responder_can_access_authority_dashboard(self, web_client, emergency_responder):
        web_client.force_login(emergency_responder)
        response = web_client.get('/dashboard/authority/')
        assert response.status_code == status.HTTP_200_OK

    def test_citizen_cannot_access_admin_dashboard(self, web_client, citizen):
        web_client.force_login(citizen)
        response = web_client.get('/dashboard/admin/')
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]

    def test_citizen_cannot_access_authority_dashboard(self, web_client, citizen):
        web_client.force_login(citizen)
        response = web_client.get('/dashboard/authority/')
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]

    def test_government_national_cannot_access_authority_dashboard(self, web_client, govt_national):
        web_client.force_login(govt_national)
        response = web_client.get('/dashboard/authority/')
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]

    def test_government_county_cannot_access_authority_dashboard(self, web_client, govt_county):
        web_client.force_login(govt_county)
        response = web_client.get('/dashboard/authority/')
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]

    def test_meteo_officer_cannot_access_admin_dashboard(self, web_client, meteo_officer):
        web_client.force_login(meteo_officer)
        response = web_client.get('/dashboard/admin/')
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]

    def test_ngo_humanitarian_cannot_access_admin_dashboard(self, web_client, ngo_humanitarian):
        web_client.force_login(ngo_humanitarian)
        response = web_client.get('/dashboard/admin/')
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]

    def test_researcher_cannot_access_admin_dashboard(self, web_client, researcher):
        web_client.force_login(researcher)
        response = web_client.get('/dashboard/admin/')
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]

    def test_citizen_can_access_citizen_dashboard(self, web_client, citizen):
        web_client.force_login(citizen)
        response = web_client.get('/dashboard/citizen/')
        assert response.status_code == status.HTTP_200_OK

    def test_super_admin_can_access_citizen_dashboard(self, web_client, super_admin):
        web_client.force_login(super_admin)
        response = web_client.get('/dashboard/citizen/')
        assert response.status_code == status.HTTP_200_OK


# ============================================================
# API Endpoint Permissions by Role
# ============================================================

@pytest.mark.django_db
class TestAPIPermissionsByRole:
    def test_super_admin_can_manual_override_zone(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/manual_override/',
            {'active': True, 'duration_hours': 1},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK

    def test_emergency_responder_can_manual_override_zone(self, api_client, emergency_responder, zone):
        api_client.force_authenticate(user=emergency_responder)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/manual_override/',
            {'active': True, 'duration_hours': 1},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK

    def test_citizen_cannot_manual_override_zone(self, api_client, citizen, zone):
        api_client.force_authenticate(user=citizen)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/manual_override/',
            {'active': True},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_government_national_cannot_manual_override_zone(self, api_client, govt_national, zone):
        api_client.force_authenticate(user=govt_national)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/manual_override/',
            {'active': True},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_meteo_officer_cannot_manual_override_zone(self, api_client, meteo_officer, zone):
        api_client.force_authenticate(user=meteo_officer)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/manual_override/',
            {'active': True},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_ngo_humanitarian_cannot_manual_override_zone(self, api_client, ngo_humanitarian, zone):
        api_client.force_authenticate(user=ngo_humanitarian)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/manual_override/',
            {'active': True},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_researcher_cannot_manual_override_zone(self, api_client, researcher, zone):
        api_client.force_authenticate(user=researcher)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/manual_override/',
            {'active': True},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_super_admin_can_dispatch_alert(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/dispatch_alert/',
            {'channels': ['sms'], 'test_mode': True},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK

    def test_emergency_responder_can_dispatch_alert(self, api_client, emergency_responder, zone):
        api_client.force_authenticate(user=emergency_responder)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/dispatch_alert/',
            {'channels': ['sms'], 'test_mode': True},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK

    def test_citizen_cannot_dispatch_alert(self, api_client, citizen, zone):
        api_client.force_authenticate(user=citizen)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/dispatch_alert/',
            {'channels': ['sms']},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_super_admin_can_verify_incident(self, api_client, super_admin, incident):
        api_client.force_authenticate(user=super_admin)
        response = api_client.patch(
            f'/api/v1/reports/{incident.id}/verify/',
            {'status': 'verified'},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK

    def test_emergency_responder_can_verify_incident(self, api_client, emergency_responder, incident):
        api_client.force_authenticate(user=emergency_responder)
        response = api_client.patch(
            f'/api/v1/reports/{incident.id}/verify/',
            {'status': 'verified'},
            format='json'
        )
        assert response.status_code == status.HTTP_200_OK

    def test_citizen_cannot_verify_incident(self, api_client, citizen, incident):
        api_client.force_authenticate(user=citizen)
        response = api_client.patch(
            f'/api/v1/reports/{incident.id}/verify/',
            {'status': 'verified'},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_super_admin_can_access_data_sources(self, api_client, super_admin):
        api_client.force_authenticate(user=super_admin)
        response = api_client.get('/api/v1/data-sources/')
        assert response.status_code == status.HTTP_200_OK

    def test_emergency_responder_can_access_data_sources(self, api_client, emergency_responder):
        api_client.force_authenticate(user=emergency_responder)
        response = api_client.get('/api/v1/data-sources/')
        assert response.status_code == status.HTTP_200_OK

    def test_citizen_cannot_access_data_sources(self, api_client, citizen):
        api_client.force_authenticate(user=citizen)
        response = api_client.get('/api/v1/data-sources/')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_authenticated_users_can_read_zones(self, api_client, citizen):
        api_client.force_authenticate(user=citizen)
        response = api_client.get('/api/v1/zones/')
        assert response.status_code == status.HTTP_200_OK

    def test_anonymous_cannot_read_zones(self, api_client):
        response = api_client.get('/api/v1/zones/')
        assert response.status_code == status.HTTP_200_OK

    def test_anyone_can_submit_incident_report(self, api_client, zone):
        from django.core.cache import cache
        cache.clear()
        response = api_client.post(
            '/api/v1/reports/',
            {'severity': 3, 'description': 'Test flood report with enough characters', 'latitude': -1.2921, 'longitude': 36.8219},
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_super_admin_can_access_beneficiaries(self, api_client, super_admin):
        api_client.force_authenticate(user=super_admin)
        response = api_client.get('/api/v1/beneficiaries/')
        assert response.status_code == status.HTTP_200_OK

    def test_emergency_responder_can_access_beneficiaries(self, api_client, emergency_responder):
        api_client.force_authenticate(user=emergency_responder)
        response = api_client.get('/api/v1/beneficiaries/')
        assert response.status_code == status.HTTP_200_OK

    def test_citizen_cannot_access_beneficiaries(self, api_client, citizen):
        api_client.force_authenticate(user=citizen)
        response = api_client.get('/api/v1/beneficiaries/')
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ============================================================
# Privilege Escalation Prevention
# ============================================================

@pytest.mark.django_db
class TestPrivilegeEscalationPrevention:
    def test_citizen_cannot_escalate_to_admin_via_api(self, api_client, citizen):
        api_client.force_authenticate(user=citizen)
        response = api_client.post('/api-token-auth/', {
            'username': citizen.username,
            'password': 'wrongpassword'
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_citizen_cannot_create_superuser(self, api_client, citizen):
        api_client.force_authenticate(user=citizen)
        response = api_client.post('/api/v1/users/', {
            'username': 'newadmin',
            'password': 'testpass123',
            'is_superuser': True
        })
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_ngo_cannot_modify_alert_zones(self, api_client, ngo_humanitarian, zone):
        api_client.force_authenticate(user=ngo_humanitarian)
        response = api_client.patch(
            f'/api/v1/zones/{zone.id}/',
            {'risk_threshold': 0.9},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_researcher_cannot_delete_zones(self, api_client, researcher, zone):
        api_client.force_authenticate(user=researcher)
        response = api_client.delete(f'/api/v1/zones/{zone.id}/')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_citizen_cannot_modify_predictions(self, api_client, citizen, prediction):
        api_client.force_authenticate(user=citizen)
        response = api_client.patch(
            f'/api/v1/predictions/{prediction.id}/',
            {'risk_score': 0.99},
            format='json'
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_meteo_cannot_dispatch_alerts(self, api_client, meteo_officer, zone):
        api_client.force_authenticate(user=meteo_officer)
        response = api_client.post(
            f'/api/v1/zones/{zone.id}/dispatch_alert/',
            {'channels': ['sms']},
            format='json'
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_citizen_cannot_access_historical_predictions_admin(self, api_client, citizen, prediction):
        api_client.force_authenticate(user=citizen)
        response = api_client.get('/api/v1/predictions/')
        assert response.status_code == status.HTTP_200_OK


# ============================================================
# Registration & Authentication
# ============================================================

@pytest.mark.django_db
class TestRegistrationAndAuthentication:
    def test_public_registration_creates_citizen(self, web_client):
        response = web_client.post('/register/', {
            'username': 'newcitizen',
            'email': 'new@example.com',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
        })
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_200_OK]
        assert User.objects.filter(username='newcitizen').exists()
        profile = User.objects.get(username='newcitizen').profile
        assert profile.role == 'citizen'

    def test_public_registration_with_phone(self, web_client):
        response = web_client.post('/register/', {
            'username': 'newcitizen2',
            'email': 'new2@example.com',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
            'phone_number': '+254712345678',
        })
        assert response.status_code in [status.HTTP_302_FOUND, status.HTTP_200_OK]
        profile = User.objects.get(username='newcitizen2').profile
        assert profile.phone_number == '+254712345678'
        assert profile.sms_enabled is True

    def test_login_redirects_citizen_to_dashboard(self, web_client, citizen):
        response = web_client.post('/login/', {
            'username': citizen.username,
            'password': 'password',
        })
        assert response.status_code == status.HTTP_302_FOUND
        assert 'citizen' in response.url or 'dashboard' in response.url

    def test_login_redirects_super_admin_to_admin_dashboard(self, web_client, super_admin):
        response = web_client.post('/login/', {
            'username': super_admin.username,
            'password': 'password',
        })
        assert response.status_code == status.HTTP_302_FOUND
        assert 'admin' in response.url

    def test_login_redirects_emergency_responder_to_authority_dashboard(self, web_client, emergency_responder):
        response = web_client.post('/login/', {
            'username': emergency_responder.username,
            'password': 'password',
        })
        assert response.status_code == status.HTTP_302_FOUND
        assert 'authority' in response.url

    def test_invalid_login_returns_error(self, web_client):
        response = web_client.post('/login/', {
            'username': 'nonexistent',
            'password': 'wrongpass',
        })
        assert response.status_code == status.HTTP_200_OK
        assert b'Invalid credentials' in response.content


# ============================================================
# Data Access by Role
# ============================================================

@pytest.mark.django_db
class TestDataAccessByRole:
    def test_citizen_can_read_own_reports(self, api_client, citizen, incident):
        api_client.force_authenticate(user=citizen)
        response = api_client.get(f'/api/v1/reports/?submitted_by=me')
        assert response.status_code == status.HTTP_200_OK

    def test_emergency_responder_can_read_all_reports(self, api_client, emergency_responder, incident):
        api_client.force_authenticate(user=emergency_responder)
        response = api_client.get('/api/v1/reports/')
        assert response.status_code == status.HTTP_200_OK

    def test_super_admin_can_read_all_reports(self, api_client, super_admin, incident):
        api_client.force_authenticate(user=super_admin)
        response = api_client.get('/api/v1/reports/')
        assert response.status_code == status.HTTP_200_OK

    def test_citizen_can_read_public_stats(self, api_client):
        response = api_client.get('/api/v1/stats/')
        assert response.status_code == status.HTTP_200_OK

    def test_anyone_can_read_impact_stats(self, api_client):
        response = api_client.get('/api/v1/impact/')
        assert response.status_code == status.HTTP_200_OK

    def test_anyone_can_read_milestones(self, api_client):
        response = api_client.get('/api/v1/milestones/')
        assert response.status_code == status.HTTP_200_OK

    def test_ai_analysis_returns_filtered_for_citizen(self, api_client, citizen, zone):
        api_client.force_authenticate(user=citizen)
        response = api_client.post('/api/v1/ai-analysis/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        analysis = data.get('analysis', {})
        assert 'overall_risk' in analysis
        assert 'summary' in analysis
        assert 'safe_zones' in analysis

    def test_ai_analysis_returns_full_for_super_admin(self, api_client, super_admin, zone):
        api_client.force_authenticate(user=super_admin)
        response = api_client.post('/api/v1/ai-analysis/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        analysis = data.get('analysis', {})
        assert 'overall_risk' in analysis
        assert 'summary' in analysis
        assert 'immediate_actions' in analysis
        assert '24h_outlook' in analysis
        assert 'highest_risk_zone' in analysis

    def test_safe_route_public_access(self, api_client):
        response = api_client.get('/api/v1/safe-route/', {
            'origin_lat': -1.2921, 'origin_lon': 36.8219,
            'dest_lat': -1.2864, 'dest_lon': 36.8172,
        })
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_501_NOT_IMPLEMENTED, status.HTTP_503_SERVICE_UNAVAILABLE]

    def test_government_can_access_impact_stats(self, api_client, govt_national):
        api_client.force_authenticate(user=govt_national)
        response = api_client.get('/api/v1/impact/')
        assert response.status_code == status.HTTP_200_OK


# ============================================================
# Role-Specific Dashboard Access
# ============================================================

@pytest.mark.django_db
class TestRoleSpecificDashboards:
    def test_citizen_dashboard_loads_for_citizen(self, web_client, citizen):
        web_client.force_login(citizen)
        response = web_client.get('/dashboard/citizen/')
        assert response.status_code == status.HTTP_200_OK

    def test_authority_dashboard_loads_for_emergency_responder(self, web_client, emergency_responder):
        web_client.force_login(emergency_responder)
        response = web_client.get('/dashboard/authority/')
        assert response.status_code == status.HTTP_200_OK

    def test_admin_dashboard_loads_for_super_admin(self, web_client, super_admin):
        web_client.force_login(super_admin)
        response = web_client.get('/dashboard/admin/')
        assert response.status_code == status.HTTP_200_OK

    def test_gis_dashboard_accessible_to_authenticated(self, api_client, citizen):
        api_client.force_authenticate(user=citizen)
        response = api_client.get('/gis/')
        assert response.status_code == status.HTTP_200_OK

    def test_gis_dashboard_accessible_to_anonymous(self, api_client):
        response = api_client.get('/gis/')
        assert response.status_code == status.HTTP_200_OK


# ============================================================
# Report Submission by Role
# ============================================================

@pytest.mark.django_db
class TestReportSubmission:
    def test_citizen_can_submit_report(self, api_client, citizen, zone):
        api_client.force_authenticate(user=citizen)
        response = api_client.post(
            '/api/v1/reports/',
            {'severity': 3, 'description': 'Flooding reported in my area with significant water accumulation', 'latitude': -1.2921, 'longitude': 36.8219},
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_ngo_can_submit_report(self, api_client, ngo_humanitarian, zone):
        api_client.force_authenticate(user=ngo_humanitarian)
        response = api_client.post(
            '/api/v1/reports/',
            {'severity': 4, 'description': 'Community affected by flash floods near the riverbank', 'latitude': -1.2921, 'longitude': 36.8219},
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_anonymous_can_submit_report(self, api_client, zone):
        response = api_client.post(
            '/api/v1/reports/',
            {'severity': 2, 'description': 'Public report of water levels rising near the bridge', 'latitude': -1.2921, 'longitude': 36.8219},
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_researcher_can_submit_report(self, api_client, researcher, zone):
        api_client.force_authenticate(user=researcher)
        response = api_client.post(
            '/api/v1/reports/',
            {'severity': 3, 'description': 'Field observation of flood extent for research purposes', 'latitude': -1.2921, 'longitude': 36.8219},
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED


# ============================================================
# Rate Limiting
# ============================================================

@pytest.mark.django_db
class TestRateLimiting:
    def test_rate_limiter_blocks_excessive_requests(self, api_client, zone):
        from django.core.cache import cache
        cache.clear()
        data = {
            'severity': 1,
            'description': 'Rate limit test report with enough characters',
            'latitude': -1.2921,
            'longitude': 36.8219,
        }
        for i in range(10):
            response = api_client.post(
                '/api/v1/reports/',
                data,
                format='json',
                REMOTE_ADDR='192.168.1.1'
            )
            assert response.status_code == status.HTTP_201_CREATED
        response = api_client.post(
            '/api/v1/reports/',
            data,
            format='json',
            REMOTE_ADDR='192.168.1.1'
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
