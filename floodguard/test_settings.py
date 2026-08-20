"""
Test-only settings that avoid PostGIS/GDAL dependency for local testing.
Uses shapely's bundled GEOS library and mocks GDAL.
"""
import os
import sys
import pathlib
from pathlib import Path
from unittest.mock import MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent

# Set GEOS_LIBRARY_PATH to use shapely's bundled GEOS
_shapely_libs = BASE_DIR / '.venv' / 'Lib' / 'site-packages' / 'shapely.libs'
geos_dll = list(_shapely_libs.glob('geos_c-*.dll'))
if geos_dll:
    GEOS_LIBRARY_PATH = str(geos_dll[0])

SECRET_KEY = 'test-secret-key-for-testing-only-1234567890'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'floodguard.urls'
WSGI_APPLICATION = 'floodguard.wsgi.application'
ASGI_APPLICATION = 'floodguard.routing.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

REDIS_URL = 'redis://localhost:6379/0'
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = False

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.InMemoryStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

USE_TZ = True
TIME_ZONE = 'UTC'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '500/hour',
        'user': '5000/hour',
        'burst': '60/minute',
    },
}

DEFAULT_GEO_BOUNDS = [33.0, -5.0, 42.0, 5.0]
GEO_BOUNDS = '33.0,-5.0,42.0,5.0'
H3_RESOLUTION = 7
H3_RESOLUTION_URBAN = 7
H3_RESOLUTION_SEMI_URBAN = 6
H3_RESOLUTION_RURAL = 5
H3_RESOLUTION_MOUNTAIN = 4
H3_RESOLUTION_COASTAL = 6

RISK_WEIGHT_DISCHARGE_CURRENT = 0.50
RISK_WEIGHT_DISCHARGE_24H = 0.30
RISK_WEIGHT_DISCHARGE_7D = 0.20
RISK_WEIGHT_PRECIP = 0.30
RISK_WEIGHT_HUMIDITY = 0.60
RISK_WEIGHT_SAR_WATER = 0.40
RISK_WEIGHT_ENVIRONMENTAL = 0.25
RISK_WEIGHT_DISCHARGE = 0.45
RISK_CONFIDENCE_PENALTY_1 = 0.80
RISK_CONFIDENCE_PENALTY_2 = 0.90

RISK_THRESHOLD_CRITICAL = 0.85
RISK_THRESHOLD_HIGH = 0.70
RISK_THRESHOLD_MODERATE = 0.40
RISK_THRESHOLD_LOW = 0.0

FLOOD_MODEL_PATH = str(BASE_DIR / 'ml_model' / 'flood_model.pkl')
GRAPHOPPER_API_KEY = ''
GRAPHOPPER_URL = 'https://graphhopper.com/api/1/route'
SAFE_ROUTE_DEFAULT_VEHICLE = 'car'

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_HOST = 'localhost'
EMAIL_PORT = 25
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
EMAIL_USE_TLS = False

SMS_ENABLED = False
AFRICASTALKING_USERNAME = 'test'
AFRICASTALKING_API_KEY = 'test'
GROQ_API_KEY = 'test'
OPENWEATHER_API_KEY = 'test'
TOMORROW_IO_API_KEY = 'test'
WEATHERAPI_KEY = 'test'
NASA_EARTHDATA_TOKEN = 'test'
GEE_SERVICE_ACCOUNT_KEY_PATH = ''

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = []
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}
