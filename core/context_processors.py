import os
import time

from django.conf import settings


def static_version(request):
    try:
        css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'style.css')
        version = str(int(os.path.getmtime(css_path)))
    except Exception:
        version = str(int(time.time()))
    return {'STATIC_VERSION': version}
