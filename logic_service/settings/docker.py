from .base import *

# Database configuration - use PostgreSQL if environment variables are set, otherwise SQLite
if os.getenv('DATABASE_ENGINE') == 'postgresql':
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
DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-4w$$of)udb)qv8=vs^5vy#8%9+kk73x0u$de0dxg2xl+@s^v1g'

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ['*']

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

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