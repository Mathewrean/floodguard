from pathlib import Path

# ==========================
# BASE DIRECTORY
# ==========================
BASE_DIR = Path(__file__).resolve().parent.parent


# ==========================
# SECURITY
# ==========================
SECRET_KEY = 'django-insecure-k_ot82dench!gnabww%=$1*_=4+)jab0q-k2si&lq*x)-pkx09'

DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0']


# ==========================
# APPLICATION DEFINITION
# ==========================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # FloodGuard Apps
    'dashboard',
    'community',
    'alerts',
    'data_ingestion',
    'monitoring',
    'rest_framework',

]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'floodguard.urls'


# ==========================
# TEMPLATES
# ==========================
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


WSGI_APPLICATION = 'floodguard.wsgi.application'


# ==========================
# DATABASE
# ==========================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ==========================
# PASSWORD VALIDATION
# ==========================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ==========================
# INTERNATIONALIZATION
# ==========================
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# ==========================
# STATIC FILES
# ==========================
STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]


# ==========================
# DEFAULT PRIMARY KEY
# ==========================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ==========================
# FLOODGUARD API SETTINGS
# ==========================
GDACS_API_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/FL"
METEOSTAT_BASE_URL = "https://meteostat.p.rapidapi.com"
NASA_GPM_BASE_URL = "https://gpm1.gesdisc.eosdis.nasa.gov"

# Thresholds (student-demo values)
FLOOD_RAINFALL_THRESHOLD_MM = 50
