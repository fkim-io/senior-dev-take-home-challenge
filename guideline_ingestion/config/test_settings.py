"""
Test-specific Django settings for guideline_ingestion project.

Inherits from base settings but overrides specific configurations for testing.
Ensures tests run in isolated environment with proper database configuration.
"""

from .settings import *  # noqa: F401, F403
import os

# Override environment for testing
ENVIRONMENT = 'testing'
IS_TESTING = True
IS_DEVELOPMENT = False
IS_PRODUCTION = False

# Test database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_TEST_DB', 'test_guideline_ingestion'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'OPTIONS': {
            'sslmode': 'prefer',
        },
        'TEST': {
            'NAME': 'test_guideline_ingestion',
        },
    }
}

# Disable migrations during tests for speed
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Use in-memory cache for testing
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
    }
}

# Celery configuration for testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# OpenAI API key not required for testing
OPENAI_API_KEY = 'test-api-key'

# Disable logging during tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['null'],
            'level': 'INFO',
            'propagate': False,
        },
        'jobs': {
            'handlers': ['null'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['null'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Faster password hashing for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable CSRF for testing
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# Test-specific settings
DEBUG = False
ALLOWED_HOSTS = ['*']

# Email backend for testing
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Media files for testing
MEDIA_ROOT = '/tmp/guideline_ingestion_test_media'

# Static files for testing
STATIC_ROOT = '/tmp/guideline_ingestion_test_static'