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
    # Ensure 4-byte emoji are supported on MySQL connections.
    if DATABASES['default'].get('ENGINE', '').endswith('.mysql'):
        DATABASES['default'].setdefault('OPTIONS', {})['charset'] = 'utf8mb4'
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

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('BREVO_SMTP_HOST', 'smtp-relay.brevo.com')
EMAIL_PORT = int(os.getenv('BREVO_SMTP_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('BREVO_SMTP_LOGIN', '')
EMAIL_HOST_PASSWORD = os.getenv('BREVO_SMTP_KEY', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'ProducerForge <hello@firstcityfoundry.com>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Session settings — persist across deploys via the database
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days
SESSION_SAVE_EVERY_REQUEST = True  # Refresh expiry on activity

# Gateway SSO — auto-login from Flask gateway's signed cookie
AUTHENTICATION_BACKENDS = [
    'production_ledger.gateway_auth.GatewayTokenBackend',
    'logic.backends.EmailOrUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]
MIDDLEWARE.insert(
    MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1,
    'production_ledger.gateway_auth.GatewaySSOMiddleware',
)
LOGIN_URL = '/'  # redirect to gateway login instead of Django's own

# Only add debug toolbar in local debug mode when package is installed.
if DEBUG and not os.getenv('RUNNING_IN_DOCKER'):
    try:
        import debug_toolbar  # noqa: F401
        MIDDLEWARE = MIDDLEWARE + ['debug_toolbar.middleware.DebugToolbarMiddleware']
        INSTALLED_APPS = INSTALLED_APPS + ["debug_toolbar"]
        INTERNAL_IPS = [
            "localhost",
            "127.0.0.1",
        ]
    except ImportError:
        pass

try:
    from .local import *
except ImportError:
    pass