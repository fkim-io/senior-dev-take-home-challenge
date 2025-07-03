"""
Test infrastructure validation tests.

These tests verify that the testing infrastructure itself is working correctly.
They test fixtures, mocks, database connectivity, and other testing utilities.
"""

import pytest
from unittest.mock import patch, Mock
import uuid
from datetime import datetime, timezone

from .mocks import (
    MockOpenAIClient,
    MockRedisClient,
    MockCeleryTask,
    mock_openai_client,
    mock_redis_client,
    mock_celery_task,
    mock_database_connection,
    TestDataManager
)
from .factories import (
    JobDataFactory,
    OpenAIResponseFactory,
    SummaryResponseFactory,
    ChecklistResponseFactory,
    APIRequestFactory,
    HealthCheckResponseFactory
)


class TestInfrastructureBase:
    """Base test class for infrastructure testing."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_data_manager = TestDataManager()
    
    def teardown_method(self):
        """Clean up after tests."""
        self.test_data_manager.cleanup()


@pytest.mark.unit
class TestDatabaseConfiguration:
    """Test database configuration for testing."""
    
    def test_database_is_configured(self):
        """Test that database is properly configured for testing."""
        from django.conf import settings
        assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'
        assert 'test_' in settings.DATABASES['default']['NAME']
    
    def test_database_connection_works(self, db):
        """Test that database connection is working."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1
    
    def test_test_database_isolation(self, db):
        """Test that test database is isolated."""
        from django.db import connection
        # This test runs in a transaction that is rolled back
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE test_isolation (id INTEGER)")
            cursor.execute("INSERT INTO test_isolation VALUES (1)")
            cursor.execute("SELECT COUNT(*) FROM test_isolation")
            result = cursor.fetchone()
            assert result[0] == 1


@pytest.mark.unit
class TestFixtures:
    """Test pytest fixtures are working correctly."""
    
    def test_api_client_fixture(self, api_client):
        """Test that API client fixture provides a working client."""
        assert hasattr(api_client, 'post')
        assert hasattr(api_client, 'get')
        assert hasattr(api_client, 'put')
        assert hasattr(api_client, 'delete')
    
    def test_sample_guidelines_fixture(self, sample_guidelines):
        """Test that sample guidelines fixture provides valid data."""
        assert isinstance(sample_guidelines, str)
        assert len(sample_guidelines) > 0
        assert "Guidelines" in sample_guidelines
    
    def test_mock_openai_responses_fixture(self, mock_openai_responses):
        """Test that mock OpenAI responses fixture provides valid data."""
        assert 'summary' in mock_openai_responses
        assert 'checklist' in mock_openai_responses
        assert mock_openai_responses['summary']['choices'][0]['message']['content']
        assert mock_openai_responses['checklist']['choices'][0]['message']['content']
    
    def test_sample_job_data_fixture(self, sample_job_data):
        """Test that sample job data fixture provides valid data."""
        assert 'guidelines' in sample_job_data
        assert 'title' in sample_job_data
        assert 'description' in sample_job_data
        assert isinstance(sample_job_data['guidelines'], str)
    
    def test_sample_event_id_fixture(self, sample_event_id):
        """Test that sample event ID fixture provides valid UUID."""
        # Should be a valid UUID string
        uuid_obj = uuid.UUID(sample_event_id)
        assert str(uuid_obj) == sample_event_id
    
    def test_performance_timer_fixture(self, performance_timer):
        """Test that performance timer fixture works correctly."""
        assert hasattr(performance_timer, 'start')
        assert hasattr(performance_timer, 'stop')
        assert hasattr(performance_timer, 'elapsed_ms')
        
        performance_timer.start()
        performance_timer.stop()
        assert performance_timer.elapsed_ms is not None
    
    def test_freeze_time_fixture(self, freeze_time):
        """Test that freeze time fixture works correctly."""
        assert isinstance(freeze_time, datetime)
        assert freeze_time.tzinfo is not None
        
        # Time should be frozen
        now1 = datetime.now(timezone.utc)
        now2 = datetime.now(timezone.utc)
        assert now1 == now2


@pytest.mark.unit
class TestMockClasses:
    """Test mock classes are working correctly."""
    
    def test_mock_openai_client(self):
        """Test MockOpenAIClient works correctly."""
        client = MockOpenAIClient()
        
        # Test summary response
        response = client.create_chat_completion([
            {"role": "user", "content": "Please summarize this text"}
        ])
        
        assert response.choices[0].message.content.startswith("Summary:")
        assert client.call_count == 1
        assert len(client.call_history) == 1
    
    def test_mock_redis_client(self):
        """Test MockRedisClient works correctly."""
        client = MockRedisClient()
        
        # Test basic operations
        assert client.ping() is True
        assert client.set('key', 'value') is True
        assert client.get('key') == 'value'
        assert client.exists('key') is True
        assert client.delete('key') is True
        assert client.exists('key') is False
        assert client.call_count == 6
    
    def test_mock_celery_task(self):
        """Test MockCeleryTask works correctly."""
        task = MockCeleryTask()
        
        # Test delay
        result = task.delay('arg1', 'arg2', kwarg1='value1')
        assert result.id == task.task_id
        assert result.args == ('arg1', 'arg2')
        assert result.kwargs == {'kwarg1': 'value1'}
        assert task.call_count == 1
    
    def test_test_data_manager(self):
        """Test TestDataManager works correctly."""
        manager = TestDataManager()
        
        # Create mock objects
        mock_obj = Mock()
        mock_obj.delete = Mock()
        
        # Add objects
        manager.add_object(mock_obj)
        manager.add_mock_client('test_client', Mock())
        
        # Test retrieval
        assert manager.get_mock_client('test_client') is not None
        assert len(manager.created_objects) == 1
        
        # Test cleanup
        manager.cleanup()
        assert len(manager.created_objects) == 0
        assert len(manager.mock_clients) == 0
        mock_obj.delete.assert_called_once()


@pytest.mark.unit
class TestFactories:
    """Test factory classes are working correctly."""
    
    def test_job_data_factory(self):
        """Test JobDataFactory creates valid data."""
        job_data = JobDataFactory()
        
        assert 'guidelines' in job_data
        assert 'title' in job_data
        assert 'description' in job_data
        assert isinstance(job_data['guidelines'], str)
        assert isinstance(job_data['title'], str)
        assert isinstance(job_data['description'], str)
    
    def test_openai_response_factory(self):
        """Test OpenAIResponseFactory creates valid responses."""
        response = OpenAIResponseFactory()
        
        assert 'id' in response
        assert 'object' in response
        assert 'created' in response
        assert 'model' in response
        assert 'choices' in response
        assert 'usage' in response
        assert response['object'] == 'chat.completion'
    
    def test_summary_response_factory(self):
        """Test SummaryResponseFactory creates valid summary responses."""
        response = SummaryResponseFactory()
        
        assert response['choices']['message']['content'].startswith('Summary:')
    
    def test_checklist_response_factory(self):
        """Test ChecklistResponseFactory creates valid checklist responses."""
        response = ChecklistResponseFactory()
        
        content = response['choices']['message']['content']
        assert 'Checklist:' in content
        assert '□' in content
    
    def test_api_request_factory(self):
        """Test APIRequestFactory creates valid requests."""
        request = APIRequestFactory.job_creation_request()
        
        assert 'guidelines' in request
        assert 'title' in request
        assert 'description' in request
        
        # Test invalid request
        invalid_request = APIRequestFactory.invalid_job_request()
        assert invalid_request['guidelines'] == ''
        assert invalid_request['title'] == ''
    
    def test_health_check_response_factory(self):
        """Test HealthCheckResponseFactory creates valid responses."""
        response = HealthCheckResponseFactory()
        
        assert 'status' in response
        assert 'database' in response
        assert 'redis' in response
        assert 'timestamp' in response
        assert 'environment' in response
        assert response['status'] in ['healthy', 'unhealthy', 'ready', 'not_ready']


@pytest.mark.unit
class TestMockContextManagers:
    """Test mock context managers work correctly."""
    
    def test_mock_openai_client_context(self):
        """Test mock_openai_client context manager."""
        with mock_openai_client() as client:
            # Client should be available and working
            assert isinstance(client, MockOpenAIClient)
            assert client.call_count == 0
    
    def test_mock_redis_client_context(self):
        """Test mock_redis_client context manager."""
        with mock_redis_client() as client:
            # Client should be available and working
            assert isinstance(client, MockRedisClient)
            assert client.call_count == 0
    
    def test_mock_celery_task_context(self):
        """Test mock_celery_task context manager."""
        with mock_celery_task() as task:
            # Task should be available and working
            assert isinstance(task, MockCeleryTask)
            assert task.call_count == 0
    
    def test_mock_database_connection_context(self):
        """Test mock_database_connection context manager."""
        with mock_database_connection() as conn:
            # Connection should be available and working
            assert hasattr(conn, 'cursor')
            assert conn.call_count == 0
            
            # Test cursor usage
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                assert result['result'] == 'test'


@pytest.mark.unit
class TestEnvironmentConfiguration:
    """Test environment configuration for testing."""
    
    def test_testing_environment_set(self):
        """Test that testing environment is properly configured."""
        from django.conf import settings
        assert settings.ENVIRONMENT == 'testing'
        assert settings.IS_TESTING is True
        assert settings.IS_DEVELOPMENT is False
        assert settings.IS_PRODUCTION is False
    
    def test_celery_eager_mode(self):
        """Test that Celery is configured for eager execution in tests."""
        from django.conf import settings
        assert settings.CELERY_TASK_ALWAYS_EAGER is True
        assert settings.CELERY_TASK_EAGER_PROPAGATES is True
        assert settings.CELERY_BROKER_URL == 'memory://'
    
    def test_openai_api_key_not_required(self):
        """Test that OpenAI API key is not required in testing."""
        from django.conf import settings
        assert settings.OPENAI_API_KEY == 'test-api-key'
    
    def test_password_hasher_fast(self):
        """Test that fast password hasher is used for testing."""
        from django.conf import settings
        assert 'MD5PasswordHasher' in settings.PASSWORD_HASHERS[0]
    
    def test_debug_disabled(self):
        """Test that DEBUG is disabled in testing."""
        from django.conf import settings
        assert settings.DEBUG is False
    
    def test_logging_disabled(self):
        """Test that logging is disabled during testing."""
        from django.conf import settings
        assert 'NullHandler' in settings.LOGGING['handlers']['null']['class']


@pytest.mark.integration
class TestDockerIntegration:
    """Test Docker integration for testing infrastructure."""
    
    def test_docker_environment_variables(self):
        """Test Docker environment variables are accessible."""
        # These should be set in the Docker environment
        import os
        
        # Check if we're running in Docker (these might not be set in local testing)
        if os.getenv('DOCKER_CONTAINER'):
            assert os.getenv('POSTGRES_HOST') is not None
            assert os.getenv('REDIS_HOST') is not None
    
    def test_service_connectivity_mocked(self):
        """Test service connectivity with mocked services."""
        with mock_database_connection() as db_conn:
            # Database connection should work
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                assert result is not None
        
        with mock_redis_client() as redis_conn:
            # Redis connection should work
            assert redis_conn.ping() is True