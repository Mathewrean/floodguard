import pytest
from django.conf import settings


settings.SECRET_KEY = settings.SECRET_KEY or 'test-secret-key'
settings.GROQ_API_KEY = getattr(settings, 'GROQ_API_KEY', '') or 'test-groq-key'
settings.SMS_ENABLED = True
settings.AFRICASTALKING_USERNAME = getattr(settings, 'AFRICASTALKING_USERNAME', '') or 'test'
settings.AFRICASTALKING_API_KEY = getattr(settings, 'AFRICASTALKING_API_KEY', '') or 'test'
settings.STORAGES = {
    **settings.STORAGES,
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


@pytest.fixture(autouse=True)
def mock_redis_for_tests(mocker):
    """Auto-mock Redis in all tests to remove infrastructure dependency"""
    mock = mocker.patch('core.tasks.redis_client')
    mock.exists.return_value = False
    mock.setex.return_value = True
    mock.delete.return_value = 1
    mock.flushdb.return_value = True
    return mock


@pytest.fixture(autouse=True)
def _disable_ssl_redirect_for_tests():
    """Ensure tests run over HTTP without 301 SSL redirects"""
    settings.SECURE_SSL_REDIRECT = False
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
