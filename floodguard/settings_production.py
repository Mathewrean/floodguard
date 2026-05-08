# Django Production Settings for FloodGuard
# This file extends settings.py with production-specific configurations
# Import all settings from the base settings module
from .settings import *  # noqa

# SECURITY WARNING: keep the secret key used in production secret!
# Already loaded from environment via project_config

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Allowed hosts for production - configure via ALLOWED_HOSTS env var
ALLOWED_HOSTS = project_config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = project_config('SECURE_SSL_REDIRECT', default=True, cast=bool)

# CSRF Configuration
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = project_config('CSRF_TRUSTED_ORIGINS', default='', cast=lambda v: [s.strip() for s in v.split(',')])

# Session Configuration
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 1209600  # 2 weeks in seconds

# CORS Configuration (if needed for separate frontend)
CORS_ALLOWED_ORIGINS = project_config('CORS_ALLOWED_ORIGINS', default='', cast=lambda v: [s.strip() for s in v.split(',')])

# Password validation already configured in base settings

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Database connection pooling (pgbouncer optional via environment)
DATABASES['default']['CONN_MAX_AGE'] = 300  # 5 minutes
DATABASES['default']['OPTIONS'] = {
    'connect_timeout': 10,
}

# Channels - use Redis in production
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
        },
    },
}

# Celery configuration for production
CELERY_BROKER_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/0'
CELERY_RESULT_BACKEND = f'redis://{REDIS_HOST}:{REDIS_PORT}/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
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
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
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
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Ensure logs directory exists
import os
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

# Rate limiting already configured in base settings

# Email configuration (for email alerts)
EMAIL_BACKEND = project_config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = project_config('EMAIL_HOST', default='localhost')
EMAIL_PORT = project_config('EMAIL_PORT', default=25, cast=int)
EMAIL_HOST_USER = project_config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = project_config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = project_config('EMAIL_USE_TLS', default=False, cast=bool)

# Africa's Talking SMS configuration
AFRICASTALKING_USERNAME = project_config('AFRICASTALKING_USERNAME')
AFRICASTALKING_API_KEY = project_config('AFRICASTALKING_API_KEY')
SMS_ENABLED = project_config('SMS_ENABLED', default=True, cast=bool)
