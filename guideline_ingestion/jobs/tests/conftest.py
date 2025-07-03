"""
Test configuration and fixtures for the jobs app.

Provides pytest fixtures and test utilities for testing job processing functionality.
Includes database fixtures, API client fixtures, and mock configurations.
"""

import pytest
from unittest.mock import Mock, patch
import uuid
from datetime import datetime, timezone

# Import Django components after Django is configured
def get_django_imports():
    """Get Django imports after Django is configured."""
    from django.test import Client
    from django.contrib.auth.models import User
    from rest_framework.test import APIClient
    return Client, User, APIClient


@pytest.fixture
def api_client():
    """Provide an APIClient instance for testing API endpoints."""
    _, _, APIClient = get_django_imports()
    return APIClient()


@pytest.fixture
def auth_user(db):
    """Create a test user for authentication-required endpoints."""
    _, User, _ = get_django_imports()
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def auth_api_client(api_client, auth_user):
    """Provide an authenticated APIClient instance."""
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.fixture
def sample_guidelines():
    """Sample guidelines text for testing job processing."""
    return """
    # Sample Guidelines Document
    
    ## Overview
    This document contains guidelines for software development practices.
    
    ## Code Quality
    - Write clean, readable code
    - Follow PEP 8 style guide
    - Use meaningful variable names
    - Add comprehensive docstrings
    
    ## Testing
    - Write unit tests for all functions
    - Maintain test coverage above 70%
    - Use pytest for testing framework
    - Mock external dependencies
    
    ## Documentation
    - Document all public APIs
    - Keep README up to date
    - Include usage examples
    """


@pytest.fixture
def mock_openai_responses():
    """Mock OpenAI API responses for testing."""
    summary_response = {
        "id": "chatcmpl-test-summary",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-3.5-turbo",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Summary: The guidelines focus on code quality, testing, and documentation best practices for software development."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 25,
            "total_tokens": 175
        }
    }
    
    checklist_response = {
        "id": "chatcmpl-test-checklist",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-3.5-turbo",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": """
                    Checklist:
                    □ Code follows PEP 8 style guide
                    □ All functions have docstrings
                    □ Unit tests written for all functions
                    □ Test coverage above 70%
                    □ Public APIs documented
                    □ README updated with usage examples
                    """
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 180,
            "completion_tokens": 45,
            "total_tokens": 225
        }
    }
    
    return {
        'summary': summary_response,
        'checklist': checklist_response
    }


@pytest.fixture
def mock_openai_client(mock_openai_responses):
    """Mock OpenAI client for testing."""
    mock_client = Mock()
    
    # Configure mock to return different responses based on call order
    mock_client.chat.completions.create.side_effect = [
        Mock(**mock_openai_responses['summary']),
        Mock(**mock_openai_responses['checklist'])
    ]
    
    return mock_client


@pytest.fixture
def mock_celery_task():
    """Mock Celery task for testing without actual task execution."""
    with patch('jobs.tasks.process_job.delay') as mock_task:
        mock_task.return_value = Mock(id=str(uuid.uuid4()))
        yield mock_task


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        'guidelines': """
        # Test Guidelines
        
        ## Quality Standards
        - Write clean code
        - Test thoroughly
        - Document properly
        """,
        'priority': 'normal',
        'metadata': {
            'source': 'test',
            'version': '1.0'
        }
    }


@pytest.fixture
def sample_event_id():
    """Sample event ID for testing."""
    return str(uuid.uuid4())


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    with patch('redis.Redis') as mock_redis:
        mock_instance = Mock()
        mock_redis.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_database_connection():
    """Mock database connection for testing connectivity."""
    with patch('django.db.connections') as mock_connections:
        mock_conn = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = Mock()
        mock_connections.__getitem__.return_value = mock_conn
        yield mock_conn


@pytest.fixture
def freeze_time():
    """Fixture to freeze time for consistent testing."""
    from freezegun import freeze_time
    frozen_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    with freeze_time(frozen_time):
        yield frozen_time


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """
    Custom database setup for testing.
    
    Ensures test database is properly configured and isolated.
    """
    with django_db_blocker.unblock():
        # Any additional database setup can be added here
        pass


@pytest.fixture
def performance_timer():
    """Fixture to measure performance of operations."""
    import time
    
    class PerformanceTimer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed_ms(self):
            if self.start_time and self.end_time:
                return (self.end_time - self.start_time) * 1000
            return None
    
    return PerformanceTimer()


@pytest.fixture
def mock_health_check_dependencies():
    """Mock external dependencies for health check testing."""
    with patch('django.db.connection.cursor') as mock_db, \
         patch('redis.Redis.ping') as mock_redis_ping:
        
        # Mock successful database connection
        mock_db.return_value.__enter__.return_value = Mock()
        
        # Mock successful Redis connection
        mock_redis_ping.return_value = True
        
        yield {
            'database': mock_db,
            'redis': mock_redis_ping
        }