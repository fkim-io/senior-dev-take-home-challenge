"""
Test factories for creating test data using factory_boy.

Provides factories for creating Job instances and related test data.
Uses factory_boy for consistent and flexible test data generation.
"""

import factory
from factory import fuzzy
from datetime import datetime, timezone
import uuid


class BaseFactory(factory.django.DjangoModelFactory):
    """Base factory with common configuration."""
    
    class Meta:
        abstract = True
    
    @classmethod
    def _setup_next_sequence(cls):
        """Override to start sequences from 1 instead of 0."""
        return 1


# Note: JobFactory will be uncommented and implemented in TASK-009
# when the Job model is fully implemented

# class JobFactory(BaseFactory):
#     """Factory for creating Job instances."""
#     
#     class Meta:
#         model = 'jobs.Job'
#     
#     event_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
#     status = fuzzy.FuzzyChoice(['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'])
#     title = factory.Faker('sentence', nb_words=3)
#     description = factory.Faker('text', max_nb_chars=200)
#     guidelines = factory.Faker('text', max_nb_chars=1000)
#     
#     # Timestamps
#     created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
#     updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
#     started_at = None
#     completed_at = None
#     
#     # Results (JSON fields)
#     result = factory.Dict({
#         'summary': factory.Faker('text', max_nb_chars=500),
#         'checklist': factory.List([
#             factory.Faker('sentence', nb_words=4) for _ in range(3)
#         ])
#     })
#     
#     # Processing metadata
#     processing_metadata = factory.Dict({
#         'worker_id': factory.Faker('uuid4'),
#         'processing_time_ms': fuzzy.FuzzyInteger(100, 5000),
#         'openai_tokens_used': fuzzy.FuzzyInteger(50, 1000)
#     })
#     
#     @factory.post_generation
#     def set_timestamps_based_on_status(self, create, extracted, **kwargs):
#         """Set appropriate timestamps based on job status."""
#         if not create:
#             return
#         
#         if self.status in ['PROCESSING', 'COMPLETED', 'FAILED']:
#             self.started_at = self.created_at
#         
#         if self.status in ['COMPLETED', 'FAILED']:
#             self.completed_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
#         
#         if create:
#             self.save()


class JobDataFactory(factory.Factory):
    """Factory for creating job data dictionaries (not model instances)."""
    
    class Meta:
        model = dict
    
    guidelines = factory.Faker('text', max_nb_chars=1000)
    priority = fuzzy.FuzzyChoice(['low', 'normal', 'high'])
    metadata = factory.Dict({
        'source': 'test',
        'version': '1.0'
    })
    
    @classmethod
    def build(cls, **kwargs):
        """Build job data dictionary."""
        return super().build(**kwargs)


class OpenAIResponseFactory(factory.Factory):
    """Factory for creating mock OpenAI API responses."""
    
    class Meta:
        model = dict
    
    id = factory.LazyFunction(lambda: f"chatcmpl-{uuid.uuid4().hex[:8]}")
    object = "chat.completion"
    created = factory.LazyFunction(lambda: int(datetime.now(timezone.utc).timestamp()))
    model = "gpt-3.5-turbo"
    
    @factory.SubFactory
    class choices(factory.Factory):
        class Meta:
            model = dict
        
        index = 0
        finish_reason = "stop"
        
        @factory.SubFactory
        class message(factory.Factory):
            class Meta:
                model = dict
            
            role = "assistant"
            content = factory.Faker('text', max_nb_chars=500)
    
    @factory.SubFactory
    class usage(factory.Factory):
        class Meta:
            model = dict
        
        prompt_tokens = fuzzy.FuzzyInteger(50, 200)
        completion_tokens = fuzzy.FuzzyInteger(20, 100)
        total_tokens = factory.LazyAttribute(lambda obj: obj.prompt_tokens + obj.completion_tokens)
    
    @classmethod
    def build_summary_response(cls, **kwargs):
        """Build a summary response."""
        return cls.build(
            choices=[{
                'index': 0,
                'finish_reason': 'stop',
                'message': {
                    'role': 'assistant',
                    'content': 'Test summary response'
                }
            }],
            **kwargs
        )


class SummaryResponseFactory(OpenAIResponseFactory):
    """Factory for creating mock OpenAI summary responses."""
    
    choices__message__content = factory.LazyFunction(
        lambda: f"Summary: This document outlines key practices and standards."
    )


class ChecklistResponseFactory(OpenAIResponseFactory):
    """Factory for creating mock OpenAI checklist responses."""
    
    choices__message__content = factory.LazyFunction(
        lambda: "Checklist:\n□ Code follows style guidelines\n□ Tests are comprehensive\n□ Documentation is complete"
    )


class ErrorResponseFactory(factory.Factory):
    """Factory for creating error response data."""
    
    class Meta:
        model = dict
    
    error = factory.Dict({
        'code': fuzzy.FuzzyChoice(['invalid_request', 'rate_limit_exceeded', 'server_error']),
        'message': factory.Faker('sentence', nb_words=8),
        'type': fuzzy.FuzzyChoice(['client_error', 'server_error']),
        'param': factory.Faker('word')
    })


class HealthCheckResponseFactory(factory.Factory):
    """Factory for creating health check response data."""
    
    class Meta:
        model = dict
    
    status = fuzzy.FuzzyChoice(['healthy', 'unhealthy', 'ready', 'not_ready'])
    database = fuzzy.FuzzyChoice(['connected', 'disconnected', 'error'])
    redis = fuzzy.FuzzyChoice(['connected', 'disconnected', 'error'])
    timestamp = factory.LazyFunction(lambda: datetime.now(timezone.utc).isoformat())
    environment = fuzzy.FuzzyChoice(['development', 'testing', 'production'])


class APIRequestFactory(factory.Factory):
    """Factory for creating API request data."""
    
    class Meta:
        model = dict
    
    @classmethod
    def job_creation_request(cls, **kwargs):
        """Create a job creation request."""
        from faker import Faker
        fake = Faker()
        return cls.build(
            guidelines=fake.text(max_nb_chars=1000),
            title=fake.sentence(nb_words=3),
            description=fake.text(max_nb_chars=200),
            **kwargs
        )
    
    @classmethod
    def invalid_job_request(cls, **kwargs):
        """Create an invalid job creation request."""
        return cls.build(
            guidelines="",  # Invalid empty guidelines
            title="",       # Invalid empty title
            **kwargs
        )
    
    @classmethod
    def build_job_create_request(cls, **kwargs):
        """Create a job creation request."""
        from faker import Faker
        fake = Faker()
        return cls.build(
            guidelines=fake.text(max_nb_chars=1000),
            priority='normal',
            **kwargs
        )


class PerformanceTestDataFactory(factory.Factory):
    """Factory for creating performance test data."""
    
    class Meta:
        model = dict
    
    @classmethod
    def create_bulk_job_data(cls, count=10):
        """Create bulk job data for performance testing."""
        return [
            JobDataFactory.build() for _ in range(count)
        ]
    
    @classmethod
    def create_concurrent_requests(cls, count=5):
        """Create data for concurrent request testing."""
        return [
            APIRequestFactory.job_creation_request() for _ in range(count)
        ]