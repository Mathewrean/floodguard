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
    # Signal creates profile automatically; view updates it if phone provided
    assert UserProfile.objects.filter(user=user).count() == 1
    assert user.profile.role == 'citizen'


@pytest.mark.django_db
def test_register_view_saves_phone_number_when_provided(client):
    """Test that phone number is saved if provided during registration"""
    response = client.post(reverse('register'), {
        'username': 'newcitizen2',
        'email': 'newcitizen2@example.com',
        'password1': 'strong-pass-123',
        'password2': 'strong-pass-123',
        'phone_number': '+254712345678'
    })
    
    assert response.status_code == 302
    
    user = User.objects.get(username='newcitizen2')
    profile = user.profile
    assert profile.phone_number == '+254712345678'
    assert profile.sms_enabled is True


@pytest.mark.django_db
def test_register_view_rejects_invalid_phone_format(client):
    """Test that registration rejects improperly formatted phone numbers"""
    response = client.post(reverse('register'), {
        'username': 'newcitizen3',
        'email': 'newcitizen3@example.com',
        'password1': 'strong-pass-123',
        'password2': 'strong-pass-123',
        'phone_number': '0712345678'  # Missing country code +
    })
    
    assert response.status_code == 200  # Form re-rendered with error
    assert b'Phone number must be in international format' in response.content
