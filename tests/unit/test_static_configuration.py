from django.conf import settings
from django.templatetags.static import static


def test_static_urls_are_root_relative_for_nested_pages():
    """Nested pages must never request `/gis/static/...` assets."""
    assert settings.STATIC_URL == '/static/'
    assert static('css/style.css').startswith('/static/')
