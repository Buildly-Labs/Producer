from .base import *
import dj_database_url

# Database configuration
# Priority: DATABASE_URL (set by DigitalOcean) > individual env vars > SQLite fallback
_db_url = os.getenv('DATABASE_URL', '')

# Strip query params (e.g. ?ssl-mode=REQUIRED) that break mysqlclient
_db_url_clean = _db_url.split('?')[0] if _db_url else ''

if _db_url_clean and '://' in _db_url_clean and not _db_url_clean.startswith('$'):
    DATABASES = {
        'default': dj_database_url.parse(
            _db_url_clean,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
    # Enable SSL for managed databases (DigitalOcean, etc.)
    if 'ssl-mode' in _db_url.lower() or 'ssl' in _db_url.lower():
        DATABASES['default'].setdefault('OPTIONS', {})['ssl'] = {'ca': None}
elif os.getenv('DATABASE_ENGINE') == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DATABASE_NAME', 'logic_service'),
            'USER': os.getenv('DATABASE_USER', 'root'),
            'PASSWORD': os.getenv('DATABASE_PASSWORD', 'root'),
            'HOST': os.getenv('DATABASE_HOST', 'localhost'),
            'PORT': os.getenv('DATABASE_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        }
    }

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-4w$$of)udb)qv8=vs^5vy#8%9+kk73x0u$de0dxg2xl+@s^v1g')

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ['*']

# Allow CSRF POST from the DO app domain and custom domains (HTTPS)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'CSRF_TRUSTED_ORIGINS',
        'https://*.ondigitalocean.app,https://market.firstcityfoundry.com'
    ).split(',')
    if origin.strip()
]

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Session settings — persist across deploys via the database
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days
SESSION_SAVE_EVERY_REQUEST = True  # Refresh expiry on activity

# Gateway SSO — auto-login from Flask gateway's signed cookie
AUTHENTICATION_BACKENDS = [
    'production_ledger.gateway_auth.GatewayTokenBackend',
    'django.contrib.auth.backends.ModelBackend',  # keep normal Django login
]
MIDDLEWARE.insert(
    MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1,
    'production_ledger.gateway_auth.GatewaySSOMiddleware',
)
LOGIN_URL = '/'  # redirect to gateway login instead of Django's own

# Only add debug toolbar and other dev-only apps when not in Docker
if not os.getenv('RUNNING_IN_DOCKER'):
    MIDDLEWARE = MIDDLEWARE + ['debug_toolbar.middleware.DebugToolbarMiddleware']
    INSTALLED_APPS = INSTALLED_APPS + ["debug_toolbar"]
    
    INTERNAL_IPS = [
        "localhost",
        "127.0.0.1",
    ]

try:
    from .local import *
except ImportError:
    pass