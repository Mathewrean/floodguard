import pytest
from django.contrib.auth.models import User
from core.models import UserProfile


pytestmark = pytest.mark.django_db


class TestDashboardE2E:
    def test_public_map_and_health_endpoints_load(self, client):
        assert client.get('/health/').status_code == 200
        # `/map/` is intentionally retained as a backwards-compatible route
        # and redirects to the current GIS dashboard.
        assert client.get('/map/', follow=True).status_code == 200
        assert client.get('/gis/').status_code == 200

    def test_citizen_login_reaches_citizen_dashboard(self, client):
        user = User.objects.create_user('citizen-e2e', password='test-pass')
        UserProfile.objects.update_or_create(user=user, defaults={'role': 'citizen'})
        response = client.post('/login/', {'username': 'citizen-e2e', 'password': 'test-pass'})
        assert response.status_code == 302
        assert response.url == '/dashboard/citizen/'

    def test_admin_role_reaches_admin_dashboard(self, client):
        user = User.objects.create_user('admin-e2e', password='test-pass')
        UserProfile.objects.update_or_create(user=user, defaults={'role': 'admin'})
        response = client.post('/login/', {'username': 'admin-e2e', 'password': 'test-pass'})
        assert response.status_code == 302
        assert response.url == '/dashboard/admin/'
