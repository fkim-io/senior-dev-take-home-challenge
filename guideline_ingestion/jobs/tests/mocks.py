"""
Mock configurations and utilities for testing.

Provides mock classes and utilities for external dependencies like OpenAI API,
Redis, and other services to ensure tests run reliably and quickly.
"""

from unittest.mock import Mock, patch, MagicMock
import uuid
import json
from datetime import datetime, timezone
from contextlib import contextmanager


class MockOpenAIClient:
    """Mock OpenAI client for testing."""
    
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_count = 0
        self.call_history = []
    
    def create_chat_completion(self, messages, model="gpt-3.5-turbo", **kwargs):
        """Mock chat completion creation."""
        self.call_count += 1
        self.call_history.append({
            'messages': messages,
            'model': model,
            'kwargs': kwargs,
            'timestamp': datetime.now(timezone.utc)
        })
        
        # Determine response type based on messages
        if any('summarize' in str(msg).lower() for msg in messages):
            return self._create_summary_response()
        elif any('checklist' in str(msg).lower() for msg in messages):
            return self._create_checklist_response()
        else:
            return self._create_default_response()
    
    def _create_summary_response(self):
        """Create a mock summary response."""
        return Mock(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            object="chat.completion",
            created=int(datetime.now(timezone.utc).timestamp()),
            model="gpt-3.5-turbo",
            choices=[
                Mock(
                    index=0,
                    message=Mock(
                        role="assistant",
                        content="Summary: This document outlines best practices for software development including code quality, testing, and documentation standards."
                    ),
                    finish_reason="stop"
                )
            ],
            usage=Mock(
                prompt_tokens=150,
                completion_tokens=35,
                total_tokens=185
            )
        )
    
    def _create_checklist_response(self):
        """Create a mock checklist response."""
        return Mock(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            object="chat.completion",
            created=int(datetime.now(timezone.utc).timestamp()),
            model="gpt-3.5-turbo",
            choices=[
                Mock(
                    index=0,
                    message=Mock(
                        role="assistant",
                        content="""Checklist:
□ Code follows established style guidelines
□ All functions have comprehensive test coverage
□ Documentation is up to date and complete
□ Error handling is implemented properly
□ Performance requirements are met"""
                    ),
                    finish_reason="stop"
                )
            ],
            usage=Mock(
                prompt_tokens=200,
                completion_tokens=45,
                total_tokens=245
            )
        )
    
    def _create_default_response(self):
        """Create a default mock response."""
        return Mock(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            object="chat.completion",
            created=int(datetime.now(timezone.utc).timestamp()),
            model="gpt-3.5-turbo",
            choices=[
                Mock(
                    index=0,
                    message=Mock(
                        role="assistant",
                        content="This is a default response for testing purposes."
                    ),
                    finish_reason="stop"
                )
            ],
            usage=Mock(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120
            )
        )


class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.data = {}
        self.call_count = 0
    
    def ping(self):
        """Mock Redis ping."""
        self.call_count += 1
        return True
    
    def set(self, key, value, ex=None):
        """Mock Redis set."""
        self.call_count += 1
        self.data[key] = {
            'value': value,
            'expires': ex,
            'timestamp': datetime.now(timezone.utc)
        }
        return True
    
    def get(self, key):
        """Mock Redis get."""
        self.call_count += 1
        return self.data.get(key, {}).get('value')
    
    def delete(self, key):
        """Mock Redis delete."""
        self.call_count += 1
        return self.data.pop(key, None) is not None
    
    def exists(self, key):
        """Mock Redis exists."""
        self.call_count += 1
        return key in self.data
    
    def flushdb(self):
        """Mock Redis flushdb."""
        self.call_count += 1
        self.data.clear()
        return True


class MockCeleryTask:
    """Mock Celery task for testing."""
    
    def __init__(self, task_id=None, result=None, status='SUCCESS'):
        self.task_id = task_id or str(uuid.uuid4())
        self.result = result
        self.status = status
        self.call_count = 0
    
    def delay(self, *args, **kwargs):
        """Mock task.delay()."""
        self.call_count += 1
        return Mock(
            id=self.task_id,
            status=self.status,
            result=self.result,
            args=args,
            kwargs=kwargs
        )
    
    def apply_async(self, *args, **kwargs):
        """Mock task.apply_async()."""
        self.call_count += 1
        return Mock(
            id=self.task_id,
            status=self.status,
            result=self.result,
            args=args,
            kwargs=kwargs
        )


class MockDatabaseConnection:
    """Mock database connection for testing."""
    
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.call_count = 0
        self.queries = []
    
    def cursor(self):
        """Mock database cursor."""
        self.call_count += 1
        if self.should_fail:
            raise Exception("Database connection failed")
        return MockCursor(self)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockCursor:
    """Mock database cursor for testing."""
    
    def __init__(self, connection):
        self.connection = connection
        self.call_count = 0
    
    def execute(self, query, params=None):
        """Mock cursor execute."""
        self.call_count += 1
        self.connection.queries.append({
            'query': query,
            'params': params,
            'timestamp': datetime.now(timezone.utc)
        })
    
    def fetchone(self):
        """Mock cursor fetchone."""
        return {'result': 'test'}
    
    def fetchall(self):
        """Mock cursor fetchall."""
        return [{'result': 'test'}]
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@contextmanager
def mock_openai_client(responses=None):
    """Context manager for mocking OpenAI client."""
    mock_client = MockOpenAIClient(responses)
    with patch('openai.OpenAI') as mock_openai:
        mock_openai.return_value.chat.completions.create = mock_client.create_chat_completion
        yield mock_client


@contextmanager
def mock_redis_client():
    """Context manager for mocking Redis client."""
    mock_client = MockRedisClient()
    with patch('redis.Redis') as mock_redis:
        mock_redis.return_value = mock_client
        yield mock_client


@contextmanager
def mock_celery_task(task_id=None, result=None, status='SUCCESS'):
    """Context manager for mocking Celery tasks."""
    mock_task = MockCeleryTask(task_id, result, status)
    with patch('jobs.tasks.process_job') as mock_process_job:
        mock_process_job.delay = mock_task.delay
        mock_process_job.apply_async = mock_task.apply_async
        yield mock_task


@contextmanager
def mock_database_connection(should_fail=False):
    """Context manager for mocking database connections."""
    mock_conn = MockDatabaseConnection(should_fail)
    with patch('django.db.connection') as mock_db_conn:
        mock_db_conn.cursor = mock_conn.cursor
        yield mock_conn


class MockPerformanceTimer:
    """Mock performance timer for testing."""
    
    def __init__(self, elapsed_ms=150):
        self.elapsed_ms = elapsed_ms
        self.start_time = None
        self.end_time = None
        self.call_count = 0
    
    def start(self):
        """Mock timer start."""
        self.call_count += 1
        self.start_time = datetime.now(timezone.utc)
    
    def stop(self):
        """Mock timer stop."""
        self.end_time = datetime.now(timezone.utc)
        return self.elapsed_ms
    
    def reset(self):
        """Reset timer."""
        self.start_time = None
        self.end_time = None
        self.call_count = 0


def create_mock_request(method='GET', path='/', data=None, headers=None):
    """Create a mock HTTP request."""
    mock_request = Mock()
    mock_request.method = method
    mock_request.path = path
    mock_request.data = data or {}
    mock_request.headers = headers or {}
    mock_request.META = {
        'HTTP_HOST': 'testserver',
        'HTTP_USER_AGENT': 'test-client',
        'REMOTE_ADDR': '127.0.0.1',
    }
    return mock_request


def create_mock_response(status_code=200, data=None, headers=None):
    """Create a mock HTTP response."""
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.data = data or {}
    mock_response.headers = headers or {}
    mock_response.content = json.dumps(data) if data else ''
    return mock_response


class TestDataManager:
    """Manage test data lifecycle."""
    
    def __init__(self):
        self.created_objects = []
        self.mock_clients = {}
    
    def add_object(self, obj):
        """Add object to cleanup list."""
        self.created_objects.append(obj)
        return obj
    
    def add_mock_client(self, name, client):
        """Add mock client to registry."""
        self.mock_clients[name] = client
        return client
    
    def cleanup(self):
        """Clean up created objects and mock clients."""
        for obj in self.created_objects:
            if hasattr(obj, 'delete'):
                try:
                    obj.delete()
                except Exception:
                    pass
        
        self.created_objects.clear()
        self.mock_clients.clear()
    
    def get_mock_client(self, name):
        """Get mock client by name."""
        return self.mock_clients.get(name)