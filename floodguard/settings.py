import os
import ssl
from pathlib import Path
from decouple import config
import dj_database_url
from celery.schedules import crontab


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def project_config(key, default=None, cast=None):
    try:
        if cast is not None:
            return config(key, default=default, cast=cast)
        return config(key, default=default)
    except Exception:
        if default is not None:
            return default
        return None


def csv_config(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [item.strip() for item in value.split(',') if item.strip()]


def redis_url_with_ssl_query(url):
    if not url or not url.startswith('rediss://') or 'ssl_cert_reqs=' in url:
        return url
    cert_reqs = project_config('REDIS_SSL_CERT_REQS', default='required')
    separator = '&' if '?' in url else '?'
    return f'{url}{separator}ssl_cert_reqs={cert_reqs}'


def redis_ssl_options():
    cert_reqs = str(project_config('REDIS_SSL_CERT_REQS', default='required')).lower()
    cert_map = {
        'none': ssl.CERT_NONE,
        'optional': ssl.CERT_OPTIONAL,
        'required': ssl.CERT_REQUIRED,
    }
    return {'ssl_cert_reqs': cert_map.get(cert_reqs, ssl.CERT_REQUIRED)}


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = project_config('SECRET_KEY', default=os.environ.get('SECRET_KEY', ''))

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = project_config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = project_config('ALLOWED_HOSTS', default='', cast=csv_config)


# Application definition

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
    'django_celery_beat',
    'corsheaders',  # CORS support
    'leaflet',
    'channels',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.SecurityHeadersMiddleware',  # Custom security headers
    'core.middleware.XRobotsTagMiddleware',  # robots tag for private pages
]

ROOT_URLCONF = 'floodguard.urls'

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
                'core.context_processors.static_version',
            ],
        },
    },
]

WSGI_APPLICATION = 'floodguard.wsgi.application'
ASGI_APPLICATION = 'floodguard.routing.application'

# Redis configuration (needed for Channels and Celery)
# Try multiple Railway-provided Redis environment variables
REDIS_URL = (
    os.environ.get('REDIS_URL') or
    os.environ.get('RAILWAY_REDIS_URL') or
    os.environ.get('DATABASE_REDIS_URL') or
    f'redis://{project_config("REDIS_HOST", default="localhost")}:{project_config("REDIS_PORT", default=6379, cast=int)}/0'
)
REDIS_URL = redis_url_with_ssl_query(REDIS_URL)

# Celery configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BEAT_SCHEDULE = {
    'fetch-flood-api': {
        'task': 'core.tasks.fetch_flood_api',
        'schedule': 900,  # every 15 minutes
    },
    'run-risk-scoring': {
        'task': 'core.tasks.run_risk_scoring',
        'schedule': 900,  # every 15 minutes
    },
    'generate-7day-forecasts': {
        'task': 'core.tasks.generate_7day_forecasts',
        'schedule': crontab(hour='*/6'),  # every 6 hours
    },
    'cluster-incident-reports': {
        'task': 'core.tasks.cluster_recent_reports',
        'schedule': crontab(hour='*/3'),  # every 3 hours
    },
    'expire-overrides': {
        'task': 'core.tasks.expire_manual_overrides',
        'schedule': 300,  # every 5 minutes
    },
}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_MAX_LOOP_INTERVAL = 300
# Concurrency will be set via --concurrency flag in Railway
if REDIS_URL and REDIS_URL.startswith('rediss://'):
    CELERY_BROKER_USE_SSL = redis_ssl_options()
    CELERY_REDIS_BACKEND_USE_SSL = redis_ssl_options()

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    }
}
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
    }
}


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': project_config('DB_NAME', default='floodguard'),
        'USER': project_config('DB_USER', default='postgres'),
        'PASSWORD': project_config('DB_PASSWORD', default=''),
        'HOST': project_config('DB_HOST', default='localhost'),
        'PORT': project_config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': project_config('DB_CONN_MAX_AGE', default=60, cast=int),  # Persistent connections for 60s
        'OPTIONS': {
            'connect_timeout': project_config('DB_CONNECT_TIMEOUT', default=10, cast=int),  # Connection timeout in seconds
        },
    }
}

DATABASE_URL = project_config('DATABASE_URL', default='')
if DATABASE_URL:
    DATABASES['default'] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=project_config('DB_CONN_MAX_AGE', default=60, cast=int),
        ssl_require=project_config('DB_SSL_REQUIRE', default=False, cast=bool),
    )
    DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'
    DATABASES['default'].setdefault('OPTIONS', {})
    DATABASES['default']['OPTIONS']['connect_timeout'] = project_config(
        'DB_CONNECT_TIMEOUT',
        default=10,
        cast=int,
    )


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Deployment/security flags can be overridden from the environment.
SECURE_SSL_REDIRECT = project_config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_REDIRECT_EXEMPT = [r'^health/$']
SESSION_COOKIE_SECURE = project_config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = project_config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_HSTS_SECONDS = project_config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = project_config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = project_config('SECURE_HSTS_PRELOAD', default=False, cast=bool)


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
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

# FloodGuard specific settings
FLOOD_MODEL_PATH = os.path.join(BASE_DIR, 'ml_model', 'flood_model.pkl')

# Geographic boundary validation (format: min_lon,min_lat,max_lon,max_lat)
# Default to Kenya/East Africa bounds; override for other regions
DEFAULT_GEO_BOUNDS = project_config(
    'GEO_BOUNDS',
    default='33.0,-5.0,42.0,5.0',  # Kenya/East Africa
    cast=lambda v: [float(c) for c in v.split(',')]
)

# Validation: ensure 4 values
if len(DEFAULT_GEO_BOUNDS) != 4:
    raise ValueError("GEO_BOUNDS must be min_lon,min_lat,max_lon,max_lat")

# External service credentials
OPENWEATHER_API_KEY = project_config('OPENWEATHER_API_KEY', default='')
TOMORROW_IO_API_KEY = project_config('TOMORROW_IO_API_KEY', default='')
WEATHERAPI_KEY = project_config('WEATHERAPI_KEY', default='')
NASA_EARTHDATA_TOKEN = project_config('NASA_EARTHDATA_TOKEN', default='')
GEE_SERVICE_ACCOUNT_KEY_PATH = project_config('GEE_SERVICE_ACCOUNT_KEY_PATH', default='')
GROQ_API_KEY = project_config('GROQ_API_KEY', default='')

# Alert delivery settings
AFRICASTALKING_USERNAME = project_config('AFRICASTALKING_USERNAME', default='')
AFRICASTALKING_API_KEY = project_config('AFRICASTALKING_API_KEY', default='')
SMS_ENABLED = project_config('SMS_ENABLED', default=True, cast=bool)

EMAIL_BACKEND = project_config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = project_config('EMAIL_HOST', default='localhost')
EMAIL_PORT = project_config('EMAIL_PORT', default=25, cast=int)
EMAIL_HOST_USER = project_config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = project_config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = project_config('EMAIL_USE_TLS', default=False, cast=bool)
DEFAULT_FROM_EMAIL = project_config('DEFAULT_FROM_EMAIL', default='FloodGuard <noreply@floodguard.com>')

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'floodguard.log',
            'formatter': 'verbose',
        },
        'error_file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'errors.log',
            'formatter': 'verbose',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'file', 'error_file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'channels': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Create logs directory

os.makedirs(BASE_DIR / 'logs', exist_ok=True)


# Railway port
PORT = project_config('PORT', default=8000, cast=int)
