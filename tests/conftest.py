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
def _configure_throttle_rates():
    """Set throttle rates to expected values for tests"""
    from core.views import ReportSubmissionThrottle, DynamicZoneThrottle, AIAnalysisThrottle
    original_report_rate = ReportSubmissionThrottle.rate
    original_dynamic_rate = DynamicZoneThrottle.rate
    original_ai_rate = AIAnalysisThrottle.rate
    ReportSubmissionThrottle.rate = '10/hour'
    DynamicZoneThrottle.rate = '60/hour'
    AIAnalysisThrottle.rate = '1000/hour'
    yield
    ReportSubmissionThrottle.rate = original_report_rate
    DynamicZoneThrottle.rate = original_dynamic_rate
    AIAnalysisThrottle.rate = original_ai_rate


@pytest.fixture(autouse=True)
def mock_redis_for_tests(mocker):
    """Auto-mock Redis in all tests to remove infrastructure dependency"""
    mock = mocker.patch('core.tasks.redis_client')
    mock.exists.return_value = False
    mock.setex.return_value = True
    mock.delete.return_value = 1
    mock.flushdb.return_value = True
    mock.ping.return_value = True
    mock.lpop.return_value = None
    mock.lpush.return_value = 1
    return mock


@pytest.fixture(autouse=True)
def _disable_ssl_redirect_for_tests():
    """Ensure tests run over HTTP without 301 SSL redirects"""
    settings.SECURE_SSL_REDIRECT = False
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
