import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from core.models import UserProfile


@pytest.mark.django_db
def test_register_view_creates_one_profile(client):
    response = client.post(reverse('register'), {
        'username': 'newcitizen',
        'email': 'newcitizen@example.com',
        'password1': 'strong-pass-123',
        'password2': 'strong-pass-123',
    })

    user = User.objects.get(username='newcitizen')

    assert response.status_code == 302
    assert response.url == reverse('citizen_dashboard')
    assert UserProfile.objects.filter(user=user).count() == 1
    assert user.profile.role == 'citizen'
