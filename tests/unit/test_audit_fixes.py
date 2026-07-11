from unittest.mock import patch

from django.urls import reverse

from core.alerts import email as email_module


def test_token_auth_endpoint_is_available():
    assert reverse('api_token_auth') == '/api-token-auth/'


def test_send_email_summary_handles_timezone_and_mail_sending():
    class DummyEmail:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def attach_alternative(self, *args, **kwargs):
            return None

        def send(self, *args, **kwargs):
            return None

    with patch.object(email_module, 'render_to_string', return_value='<p>hello</p>'), patch.object(email_module, 'EmailMultiAlternatives', DummyEmail):
        assert email_module.send_email_summary('user@example.com', [{'zone': 'North'}]) is True
