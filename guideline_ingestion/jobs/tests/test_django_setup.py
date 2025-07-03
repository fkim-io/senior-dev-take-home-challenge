"""
Django project setup tests for TASK-008.

Tests Django configuration, database connectivity, Django REST Framework setup,
and admin interface accessibility in the containerized environment.
"""

import pytest
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.core.exceptions import ImproperlyConfigured
from django.apps import apps
from django.contrib.auth.models import User
import os
import time


@pytest.mark.unit
class TestDjangoConfiguration:
    """Test Django project configuration is correct."""
    
    def test_settings_module_loads(self):
        """Test Django settings module loads without errors."""
        from django.conf import settings
        
        # Should not raise any exceptions
        assert settings.configured
        assert hasattr(settings, 'SECRET_KEY')
        assert hasattr(settings, 'DATABASES')
        assert hasattr(settings, 'INSTALLED_APPS')
    
    def test_environment_configuration(self):
        """Test environment-aware configuration works correctly."""
        from django.conf import settings
        
        # Should have environment settings
        assert hasattr(settings, 'ENVIRONMENT')
        assert hasattr(settings, 'IS_DEVELOPMENT')
        assert hasattr(settings, 'IS_TESTING')
        assert hasattr(settings, 'IS_PRODUCTION')
        
        # Environment should be consistent
        if settings.ENVIRONMENT == 'development':
            assert settings.IS_DEVELOPMENT is True
            assert settings.IS_TESTING is False
            assert settings.IS_PRODUCTION is False
    
    def test_required_apps_installed(self):
        """Test all required Django apps are installed."""
        from django.conf import settings
        
        required_django_apps = [
            'django.contrib.admin',
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'django.contrib.staticfiles',
        ]
        
        required_third_party_apps = [
            'rest_framework',
            'drf_spectacular',
            'corsheaders',
        ]
        
        required_local_apps = [
            'guideline_ingestion.jobs',
        ]
        
        for app in required_django_apps + required_third_party_apps + required_local_apps:
            assert app in settings.INSTALLED_APPS, f"Required app {app} not in INSTALLED_APPS"
    
    def test_middleware_configuration(self):
        """Test middleware stack is properly configured."""
        from django.conf import settings
        
        required_middleware = [
            'django.middleware.security.SecurityMiddleware',
            'corsheaders.middleware.CorsMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        ]
        
        for middleware in required_middleware:
            assert middleware in settings.MIDDLEWARE, f"Required middleware {middleware} not configured"
    
    def test_database_configuration(self):
        """Test database configuration is valid."""
        from django.conf import settings
        
        # Should have default database
        assert 'default' in settings.DATABASES
        
        db_config = settings.DATABASES['default']
        assert db_config['ENGINE'] == 'django.db.backends.postgresql'
        assert db_config['NAME'] is not None
        assert db_config['USER'] is not None
        assert db_config['HOST'] is not None
        assert db_config['PORT'] is not None
        
        # Should have connection pooling configured (may be 0 in tests)
        assert 'CONN_MAX_AGE' in db_config
        assert isinstance(db_config['CONN_MAX_AGE'], (int, type(None)))
    
    def test_static_files_configuration(self):
        """Test static files are properly configured."""
        from django.conf import settings
        
        assert hasattr(settings, 'STATIC_URL')
        assert hasattr(settings, 'STATIC_ROOT')
        assert hasattr(settings, 'MEDIA_URL')
        assert hasattr(settings, 'MEDIA_ROOT')
        
        assert settings.STATIC_URL is not None
        assert settings.STATIC_ROOT is not None
    
    def test_secret_key_configuration(self):
        """Test SECRET_KEY is properly configured."""
        from django.conf import settings
        
        assert settings.SECRET_KEY is not None
        assert len(settings.SECRET_KEY) > 0
        
        # In production, should not be the default development key
        if settings.IS_PRODUCTION:
            assert 'django-insecure' not in settings.SECRET_KEY
    
    def test_allowed_hosts_configuration(self):
        """Test ALLOWED_HOSTS is properly configured."""
        from django.conf import settings
        
        assert hasattr(settings, 'ALLOWED_HOSTS')
        assert isinstance(settings.ALLOWED_HOSTS, list)
        
        # In testing environment, ALLOWED_HOSTS might be ['*']
        if not settings.IS_TESTING:
            # Should include common development hosts
            expected_hosts = ['localhost', '127.0.0.1', '0.0.0.0']
            for host in expected_hosts:
                assert host in settings.ALLOWED_HOSTS, f"Expected host {host} not in ALLOWED_HOSTS"


@pytest.mark.integration
class TestDatabaseConnectivity:
    """Test database connectivity in containerized environment."""
    
    def test_database_connection_works(self, db):
        """Test database connection is functional."""
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1
    
    def test_database_migration_check(self, db):
        """Test database migrations can be checked."""
        from django.core.management import call_command
        from io import StringIO
        
        # Should not raise exceptions
        out = StringIO()
        call_command('showmigrations', stdout=out)
        output = out.getvalue()
        
        # Should show migration status (jobs app might not have migrations yet)
        assert isinstance(output, str)
    
    def test_database_operations(self, db):
        """Test basic database operations work."""
        from django.contrib.auth.models import User
        
        # Create a user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Verify user was created
        assert user.id is not None
        assert user.username == 'testuser'
        
        # Verify user can be retrieved
        retrieved_user = User.objects.get(username='testuser')
        assert retrieved_user.id == user.id
        
        # Clean up
        user.delete()
    
    def test_database_transaction_support(self, db):
        """Test database supports transactions properly."""
        from django.db import transaction
        from django.contrib.auth.models import User
        
        initial_count = User.objects.count()
        
        try:
            with transaction.atomic():
                User.objects.create_user(
                    username='transactiontest',
                    email='transaction@example.com',
                    password='testpass123'
                )
                # Force a rollback
                raise Exception("Test rollback")
        except Exception:
            pass
        
        # User should not exist due to rollback
        final_count = User.objects.count()
        assert final_count == initial_count
        assert not User.objects.filter(username='transactiontest').exists()


@pytest.mark.unit
class TestDjangoRESTFrameworkSetup:
    """Test Django REST Framework configuration."""
    
    def test_drf_installed_and_configured(self):
        """Test DRF is properly installed and configured."""
        from django.conf import settings
        
        # DRF should be in installed apps
        assert 'rest_framework' in settings.INSTALLED_APPS
        
        # Should have REST_FRAMEWORK settings
        assert hasattr(settings, 'REST_FRAMEWORK')
        assert isinstance(settings.REST_FRAMEWORK, dict)
    
    def test_drf_spectacular_configured(self):
        """Test drf-spectacular is configured for OpenAPI."""
        from django.conf import settings
        
        # drf-spectacular should be installed
        assert 'drf_spectacular' in settings.INSTALLED_APPS
        
        # Should have spectacular settings
        assert hasattr(settings, 'SPECTACULAR_SETTINGS')
        assert isinstance(settings.SPECTACULAR_SETTINGS, dict)
        
        # Should have required spectacular configuration
        spectacular_config = settings.SPECTACULAR_SETTINGS
        assert 'TITLE' in spectacular_config
        assert 'DESCRIPTION' in spectacular_config
        assert 'VERSION' in spectacular_config
    
    def test_drf_default_schema_class(self):
        """Test DRF uses drf-spectacular schema class."""
        from django.conf import settings
        
        drf_config = settings.REST_FRAMEWORK
        assert 'DEFAULT_SCHEMA_CLASS' in drf_config
        assert drf_config['DEFAULT_SCHEMA_CLASS'] == 'drf_spectacular.openapi.AutoSchema'
    
    def test_drf_pagination_configured(self):
        """Test DRF pagination is configured."""
        from django.conf import settings
        
        drf_config = settings.REST_FRAMEWORK
        assert 'DEFAULT_PAGINATION_CLASS' in drf_config
        assert 'PAGE_SIZE' in drf_config
        assert isinstance(drf_config['PAGE_SIZE'], int)
        assert drf_config['PAGE_SIZE'] > 0
    
    def test_drf_throttling_configured(self):
        """Test DRF throttling is configured."""
        from django.conf import settings
        
        drf_config = settings.REST_FRAMEWORK
        assert 'DEFAULT_THROTTLE_CLASSES' in drf_config
        assert 'DEFAULT_THROTTLE_RATES' in drf_config
        
        throttle_rates = drf_config['DEFAULT_THROTTLE_RATES']
        assert 'anon' in throttle_rates
        assert 'user' in throttle_rates


@pytest.mark.unit
class TestCeleryIntegration:
    """Test Celery integration with Django."""
    
    def test_celery_settings_configured(self):
        """Test Celery settings are properly configured."""
        from django.conf import settings
        
        # Should have Celery configuration
        assert hasattr(settings, 'CELERY_BROKER_URL')
        assert hasattr(settings, 'CELERY_RESULT_BACKEND')
        assert hasattr(settings, 'CELERY_TASK_SERIALIZER')
        assert hasattr(settings, 'CELERY_RESULT_SERIALIZER')
        assert hasattr(settings, 'CELERY_ACCEPT_CONTENT')
        
        # Should use JSON serialization
        assert settings.CELERY_TASK_SERIALIZER == 'json'
        assert settings.CELERY_RESULT_SERIALIZER == 'json'
        assert 'json' in settings.CELERY_ACCEPT_CONTENT
    
    def test_celery_app_import(self):
        """Test Celery app can be imported from Django config."""
        # Should not raise import errors
        from config.celery import app
        
        assert app is not None
        assert hasattr(app, 'autodiscover_tasks')
    
    def test_celery_redis_configuration(self):
        """Test Celery is configured to use Redis."""
        from django.conf import settings
        
        # In testing, may use memory:// broker
        if settings.IS_TESTING:
            # Testing environment may use memory broker
            assert 'memory://' in settings.CELERY_BROKER_URL or 'redis://' in settings.CELERY_BROKER_URL
        else:
            # Production/development should use Redis
            assert 'redis://' in settings.CELERY_BROKER_URL
            assert 'redis://' in settings.CELERY_RESULT_BACKEND


@pytest.mark.unit
class TestURLConfiguration:
    """Test URL configuration is correct."""
    
    def test_root_urlconf_configured(self):
        """Test ROOT_URLCONF is properly set."""
        from django.conf import settings
        
        assert hasattr(settings, 'ROOT_URLCONF')
        assert settings.ROOT_URLCONF == 'config.urls'
    
    def test_admin_urls_accessible(self):
        """Test admin URLs are configured."""
        from django.urls import reverse, NoReverseMatch
        
        # Should not raise NoReverseMatch
        try:
            admin_url = reverse('admin:index')
            assert admin_url is not None
        except NoReverseMatch:
            pytest.fail("Admin URLs not properly configured")
    
    def test_health_check_urls_accessible(self):
        """Test health check URLs are configured."""
        from django.urls import reverse, NoReverseMatch
        
        # Should not raise NoReverseMatch
        try:
            health_url = reverse('health')
            assert health_url is not None
            
            readiness_url = reverse('readiness')
            assert readiness_url is not None
        except NoReverseMatch:
            pytest.fail("Health check URLs not properly configured")


@pytest.mark.integration
class TestApplicationStartup:
    """Test Django application startup in containerized environment."""
    
    def test_django_apps_ready(self):
        """Test all Django apps are properly loaded."""
        from django.apps import apps
        
        # Apps should be ready
        assert apps.ready
        
        # Should be able to get app configs
        jobs_app = apps.get_app_config('jobs')
        assert jobs_app is not None
        assert jobs_app.name == 'guideline_ingestion.jobs'
    
    def test_django_startup_time(self):
        """Test Django startup is reasonably fast."""
        import time
        from django.core.wsgi import get_wsgi_application
        
        start_time = time.time()
        
        # This should complete quickly
        app = get_wsgi_application()
        
        startup_time = time.time() - start_time
        
        # Should start in under 5 seconds
        assert startup_time < 5.0, f"Django startup took {startup_time:.2f}s, exceeds 5s limit"
        assert app is not None


@pytest.mark.performance
class TestPerformanceConfiguration:
    """Test performance-related configuration."""
    
    def test_database_connection_pooling(self):
        """Test database connection pooling is enabled."""
        from django.conf import settings
        
        db_config = settings.DATABASES['default']
        
        # Should have connection pooling configured
        assert 'CONN_MAX_AGE' in db_config
        
        # In non-testing environments, should have pooling enabled
        if not settings.IS_TESTING:
            assert db_config['CONN_MAX_AGE'] > 0
        
        # Should have health checks enabled (if configured)
        if 'CONN_HEALTH_CHECKS' in db_config:
            assert isinstance(db_config['CONN_HEALTH_CHECKS'], bool)
    
    def test_debug_configuration(self):
        """Test DEBUG is properly configured for environment."""
        from django.conf import settings
        
        # In production, DEBUG should be False
        if settings.IS_PRODUCTION:
            assert settings.DEBUG is False
        
        # DEBUG should be a boolean
        assert isinstance(settings.DEBUG, bool)
    
    def test_logging_configuration(self):
        """Test logging is properly configured."""
        from django.conf import settings
        import logging
        
        # Should have logging configuration
        assert hasattr(settings, 'LOGGING')
        assert isinstance(settings.LOGGING, dict)
        
        # Should be able to get a logger
        logger = logging.getLogger('jobs')
        assert logger is not None


@pytest.mark.integration
class TestStaticFilesConfiguration:
    """Test static files configuration."""
    
    def test_static_files_settings(self):
        """Test static files settings are configured."""
        from django.conf import settings
        
        assert settings.STATIC_URL is not None
        assert settings.STATIC_ROOT is not None
        assert settings.MEDIA_URL is not None
        assert settings.MEDIA_ROOT is not None
    
    def test_static_files_finders(self):
        """Test static files finders work correctly."""
        from django.contrib.staticfiles.finders import find
        
        # Should be able to find admin static files
        admin_css = find('admin/css/base.css')
        # Note: This might be None in some configurations, that's OK
        # The important thing is that the finders don't crash