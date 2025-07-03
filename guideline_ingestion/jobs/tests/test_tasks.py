"""
Tests for Celery tasks and worker functionality (TDD Red Phase).

This module contains comprehensive tests for async job processing,
Celery configuration, error handling, and Redis integration.
"""

import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call

import pytest
from celery import current_app
from celery.exceptions import Retry
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.db import DatabaseError

from guideline_ingestion.jobs.models import Job, JobStatus
from guideline_ingestion.jobs.tasks import process_guideline_job


class TestCeleryConfiguration(TestCase):
    """Test Celery application configuration and setup."""
    
    def test_celery_app_configured(self):
        """Test that Celery app is properly configured."""
        self.assertIsNotNone(current_app)
        self.assertEqual(current_app.main, 'guideline_ingestion')
    
    def test_celery_task_discovery(self):
        """Test that Celery discovers tasks from jobs app."""
        task_names = [task for task in current_app.tasks.keys()]
        
        # Should include our custom task
        self.assertIn('guideline_ingestion.jobs.tasks.process_guideline_job', task_names)
        
        # Should include debug task from celery config
        self.assertIn('config.celery.debug_task', task_names)
    
    def test_celery_configuration_settings(self):
        """Test Celery configuration values."""
        config = current_app.conf
        
        # Task serialization settings
        self.assertEqual(config.task_serializer, 'json')
        self.assertEqual(config.result_serializer, 'json')
        self.assertIn('json', config.accept_content)
        
        # Timezone and UTC settings
        self.assertEqual(config.timezone, 'UTC')
        self.assertTrue(config.enable_utc)
        
        # Worker settings
        self.assertEqual(config.worker_prefetch_multiplier, 1)
        self.assertTrue(config.task_acks_late)
        self.assertTrue(config.task_reject_on_worker_lost)
        
        # Retry settings
        self.assertEqual(config.task_default_retry_delay, 60)
        self.assertEqual(config.task_max_retries, 3)
    
    def test_celery_task_registration(self):
        """Test that process_guideline_job task is properly registered."""
        task = current_app.tasks.get('guideline_ingestion.jobs.tasks.process_guideline_job')
        
        self.assertIsNotNone(task)
        self.assertEqual(task.name, 'guideline_ingestion.jobs.tasks.process_guideline_job')
    
    def test_celery_result_backend_configuration(self):
        """Test result backend is configured for job tracking."""
        # In test environment, should use memory backend
        # In production, should use Redis
        config = current_app.conf
        
        # Result expiration should be set
        self.assertEqual(config.result_expires, 3600)


class TestJobProcessingTask(TransactionTestCase):
    """Test job processing task functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_guidelines = """
        Security Guidelines for API Development:
        1. Always use HTTPS for API endpoints
        2. Implement proper authentication and authorization
        3. Validate all input data thoroughly
        4. Use rate limiting to prevent abuse
        5. Log security events for monitoring
        """
        
        self.job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={
                'guidelines': self.valid_guidelines,
                'priority': 'normal'
            }
        )
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_guideline_job_success(self, mock_gpt_process):
        """Test successful job processing."""
        # Mock GPT processing results
        mock_gpt_process.return_value = {
            'summary': 'Security guidelines for API development focusing on HTTPS, authentication, and monitoring.',
            'checklist': [
                {
                    'id': 1,
                    'title': 'Implement HTTPS',
                    'description': 'Ensure all API endpoints use HTTPS encryption',
                    'priority': 'high',
                    'category': 'security'
                },
                {
                    'id': 2,
                    'title': 'Add Authentication',
                    'description': 'Implement proper authentication mechanisms',
                    'priority': 'high',
                    'category': 'security'
                }
            ]
        }
        
        # Execute task
        result = process_guideline_job(self.job.id, self.valid_guidelines)
        
        # Verify task completed successfully
        self.assertIsNotNone(result)
        
        # Verify job status updated
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(self.job.result)
        self.assertIn('summary', self.job.result)
        self.assertIn('checklist', self.job.result)
        
        # Verify timestamps
        self.assertIsNotNone(self.job.started_at)
        self.assertIsNotNone(self.job.completed_at)
        self.assertGreater(self.job.completed_at, self.job.started_at)
        
        # Verify GPT processing was called
        mock_gpt_process.assert_called_once_with(self.valid_guidelines)
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_guideline_job_marks_processing(self, mock_gpt_process):
        """Test job is marked as processing when task starts."""
        # Mock slow GPT processing
        def slow_processing(guidelines):
            time.sleep(0.1)  # Small delay to test timing
            return {
                'summary': 'Test summary',
                'checklist': []
            }
        
        mock_gpt_process.side_effect = slow_processing
        
        # Execute task
        process_guideline_job(self.job.id, self.valid_guidelines)
        
        # Verify job was marked as processing and then completed
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(self.job.started_at)
    
    def test_process_guideline_job_invalid_job_id(self):
        """Test handling of invalid job ID."""
        invalid_job_id = 99999
        
        with self.assertRaises(Exception):
            process_guideline_job(invalid_job_id, self.valid_guidelines)
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_guideline_job_gpt_error(self, mock_gpt_process):
        """Test handling of GPT processing errors."""
        # Mock GPT processing failure
        mock_gpt_process.side_effect = Exception("OpenAI API error")
        
        # Execute task - should handle error gracefully
        with self.assertRaises(Exception):
            process_guideline_job(self.job.id, self.valid_guidelines)
        
        # Verify job marked as failed
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.assertIsNotNone(self.job.error_message)
        self.assertIn("OpenAI API error", self.job.error_message)
        self.assertIsNotNone(self.job.completed_at)
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_guideline_job_database_error(self, mock_gpt_process):
        """Test handling of database errors during processing."""
        mock_gpt_process.return_value = {
            'summary': 'Test summary',
            'checklist': []
        }
        
        # Delete job to simulate database error
        job_id = self.job.id
        self.job.delete()
        
        with self.assertRaises(Exception):
            process_guideline_job(job_id, self.valid_guidelines)
    
    def test_process_guideline_job_empty_guidelines(self):
        """Test handling of empty guidelines."""
        empty_guidelines = ""
        
        with self.assertRaises(Exception) as context:
            process_guideline_job(self.job.id, empty_guidelines)
        
        self.assertIn("Guidelines cannot be empty", str(context.exception))
        
        # Verify job marked as failed
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.FAILED)
    
    def test_process_guideline_job_already_processing(self):
        """Test handling of job already in processing state."""
        # Mark job as already processing
        self.job.mark_as_processing()
        
        # Should not process again
        with self.assertRaises(Exception) as context:
            process_guideline_job(self.job.id, self.valid_guidelines)
        
        self.assertIn("already being processed", str(context.exception))


class TestJobStatusUpdates(TestCase):
    """Test job status update functionality."""
    
    def setUp(self):
        """Set up test job."""
        self.job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Test guidelines'}
        )
    
    def test_job_mark_as_processing(self):
        """Test marking job as processing."""
        original_updated_at = self.job.updated_at
        
        self.job.mark_as_processing()
        
        self.assertEqual(self.job.status, JobStatus.PROCESSING)
        self.assertIsNotNone(self.job.started_at)
        self.assertGreater(self.job.updated_at, original_updated_at)
    
    def test_job_mark_as_completed(self):
        """Test marking job as completed with results."""
        self.job.mark_as_processing()
        
        result_data = {
            'summary': 'Test summary',
            'checklist': [{'id': 1, 'title': 'Test item'}]
        }
        
        self.job.mark_as_completed(result_data)
        
        self.assertEqual(self.job.status, JobStatus.COMPLETED)
        self.assertEqual(self.job.result, result_data)
        self.assertIsNotNone(self.job.completed_at)
        self.assertIsNone(self.job.error_message)
    
    def test_job_mark_as_failed(self):
        """Test marking job as failed with error message."""
        self.job.mark_as_processing()
        
        error_message = "Test error occurred"
        self.job.mark_as_failed(error_message)
        
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.assertEqual(self.job.error_message, error_message)
        self.assertIsNotNone(self.job.completed_at)
    
    def test_job_increment_retry_count(self):
        """Test incrementing retry count."""
        original_count = self.job.retry_count
        
        self.job.increment_retry_count()
        
        self.assertEqual(self.job.retry_count, original_count + 1)


class TestErrorHandlingAndRetry(TransactionTestCase):
    """Test error handling and retry logic for tasks."""
    
    def setUp(self):
        """Set up test job."""
        self.job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Test guidelines'}
        )
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_task_retry_on_temporary_error(self, mock_gpt_process):
        """Test task retries on temporary errors."""
        # Mock temporary error (e.g., rate limiting)
        mock_gpt_process.side_effect = Exception("Rate limit exceeded")
        
        # Get the actual task instance to test retry behavior
        task = process_guideline_job
        
        with patch.object(task, 'retry') as mock_retry:
            mock_retry.side_effect = Retry("Retrying due to rate limit")
            
            with self.assertRaises(Retry):
                task(self.job.id, 'Test guidelines')
            
            # Verify retry was called
            mock_retry.assert_called_once()
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_task_max_retries_exceeded(self, mock_gpt_process):
        """Test task behavior when max retries exceeded."""
        # Mock persistent error
        mock_gpt_process.side_effect = Exception("Persistent API error")
        
        # Simulate max retries exceeded
        self.job.retry_count = 3
        self.job.save()
        
        with self.assertRaises(Exception):
            process_guideline_job(self.job.id, 'Test guidelines')
        
        # Verify job marked as failed
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.assertIn("Persistent API error", self.job.error_message)
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_task_retry_with_exponential_backoff(self, mock_gpt_process):
        """Test retry with exponential backoff calculation."""
        mock_gpt_process.side_effect = Exception("Temporary error")
        
        task = process_guideline_job
        
        with patch.object(task, 'retry') as mock_retry:
            mock_retry.side_effect = Retry("Retrying with backoff")
            
            # Set retry count to test backoff calculation
            self.job.retry_count = 1
            self.job.save()
            
            with self.assertRaises(Retry):
                task(self.job.id, 'Test guidelines')
            
            # Verify retry was called with backoff
            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args[1]
            self.assertIn('countdown', call_kwargs)
    
    def test_task_error_categorization(self):
        """Test different error types are handled appropriately."""
        test_cases = [
            ("Rate limit exceeded", True),  # Should retry
            ("Invalid API key", False),     # Should not retry
            ("Network timeout", True),      # Should retry
            ("Invalid input format", False) # Should not retry
        ]
        
        for error_message, should_retry in test_cases:
            with self.subTest(error=error_message):
                # This would test error categorization logic
                # Implementation depends on actual error handling strategy
                pass


class TestConcurrentJobProcessing(TransactionTestCase):
    """Test concurrent job processing scenarios."""
    
    def setUp(self):
        """Set up multiple test jobs."""
        self.jobs = []
        for i in range(3):
            job = Job.objects.create(
                status=JobStatus.PENDING,
                input_data={'guidelines': f'Test guidelines {i}'}
            )
            self.jobs.append(job)
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_multiple_jobs_processed_concurrently(self, mock_gpt_process):
        """Test multiple jobs can be processed concurrently."""
        # Mock GPT processing with different results
        def mock_processing(guidelines):
            return {
                'summary': f'Summary for: {guidelines}',
                'checklist': []
            }
        
        mock_gpt_process.side_effect = mock_processing
        
        # Process all jobs
        for job in self.jobs:
            process_guideline_job(job.id, job.input_data['guidelines'])
        
        # Verify all jobs completed
        for job in self.jobs:
            job.refresh_from_db()
            self.assertEqual(job.status, JobStatus.COMPLETED)
            self.assertIsNotNone(job.result)
    
    def test_job_processing_isolation(self):
        """Test that job processing failures don't affect other jobs."""
        # This would test that if one job fails, others continue processing
        # Implementation depends on actual concurrency strategy
        pass
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_job_queue_ordering(self, mock_gpt_process):
        """Test that jobs are processed in correct order."""
        mock_gpt_process.return_value = {
            'summary': 'Test summary',
            'checklist': []
        }
        
        # Create jobs with different priorities
        high_priority_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'High priority guidelines', 'priority': 'high'}
        )
        
        low_priority_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Low priority guidelines', 'priority': 'low'}
        )
        
        # In a real implementation, high priority jobs should be processed first
        # This test would verify queue ordering logic
        pass


class TestTaskPerformance(TestCase):
    """Test task performance and monitoring."""
    
    def setUp(self):
        """Set up test job."""
        self.job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Performance test guidelines'}
        )
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_task_execution_time_tracking(self, mock_gpt_process):
        """Test that task execution time is tracked."""
        mock_gpt_process.return_value = {
            'summary': 'Test summary',
            'checklist': []
        }
        
        start_time = timezone.now()
        process_guideline_job(self.job.id, 'Test guidelines')
        
        self.job.refresh_from_db()
        
        # Verify timing information is recorded
        self.assertIsNotNone(self.job.started_at)
        self.assertIsNotNone(self.job.completed_at)
        self.assertGreaterEqual(self.job.started_at, start_time)
        self.assertGreater(self.job.completed_at, self.job.started_at)
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_task_timeout_handling(self, mock_gpt_process):
        """Test handling of task timeouts."""
        # Mock very slow processing
        def slow_processing(guidelines):
            time.sleep(2)  # Simulate slow processing
            return {'summary': 'Slow summary', 'checklist': []}
        
        mock_gpt_process.side_effect = slow_processing
        
        # In a real implementation, this would test timeout handling
        # For now, just verify the task completes
        process_guideline_job(self.job.id, 'Test guidelines')
        
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.COMPLETED)


class TestRedisIntegration(TestCase):
    """Test Redis queue integration."""
    
    def test_task_queuing_to_redis(self):
        """Test that tasks are properly queued to Redis."""
        # This would test Redis broker integration
        # In test environment, using memory broker
        
        job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Redis test guidelines'}
        )
        
        # Queue task
        task_result = process_guideline_job.delay(job.id, 'Test guidelines')
        
        # Verify task was queued
        self.assertIsNotNone(task_result.id)
    
    def test_task_result_storage(self):
        """Test that task results are stored in Redis."""
        # This would test result backend functionality
        # Implementation depends on Redis result backend configuration
        pass
    
    def test_dead_letter_queue_handling(self):
        """Test handling of failed tasks in dead letter queue."""
        # This would test dead letter queue configuration
        # Implementation depends on Celery dead letter queue setup
        pass


class TestGPTProcessingFunction(TestCase):
    """Test the process_guidelines_with_gpt function with comprehensive scenarios."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_guidelines = """
        Security Guidelines for API Development:
        1. Always use HTTPS for API endpoints
        2. Implement proper authentication and authorization
        3. Validate all input data thoroughly
        4. Use rate limiting to prevent abuse
        5. Log security events for monitoring
        """
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_success(self, mock_gpt_client_class, mock_getattr):
        """Test successful GPT processing with proper configuration."""
        from guideline_ingestion.jobs.tasks import process_guidelines_with_gpt
        
        # Mock settings
        mock_getattr.side_effect = lambda obj, key, default=None: {
            'OPENAI_API_KEY': 'test-api-key',
            'OPENAI_MODEL': 'gpt-4',
            'OPENAI_MAX_TOKENS': 2000,
            'OPENAI_TEMPERATURE': 0.1,
            'OPENAI_RATE_LIMIT_REQUESTS': 60,
            'OPENAI_RATE_LIMIT_WINDOW': 60
        }.get(key, default)
        
        # Mock GPT client
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        
        expected_result = {
            'summary': 'Security guidelines for API development',
            'checklist': [
                {
                    'id': 1,
                    'title': 'Implement HTTPS',
                    'description': 'Ensure all API endpoints use HTTPS',
                    'priority': 'high',
                    'category': 'security'
                }
            ]
        }
        mock_client.process_guidelines.return_value = expected_result
        
        # Execute function
        result = process_guidelines_with_gpt(self.valid_guidelines)
        
        # Verify result
        self.assertEqual(result, expected_result)
        
        # Verify GPT client was initialized with correct parameters
        mock_gpt_client_class.assert_called_once_with(
            api_key='test-api-key',
            model='gpt-4',
            max_tokens=2000,
            temperature=0.1,
            rate_limit_requests=60,
            rate_limit_window=60
        )
        
        # Verify process_guidelines was called
        mock_client.process_guidelines.assert_called_once_with(self.valid_guidelines)
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    def test_process_guidelines_with_gpt_missing_api_key(self, mock_getattr):
        """Test GPT processing with missing API key."""
        from guideline_ingestion.jobs.tasks import process_guidelines_with_gpt, PermanentProcessingError
        
        # Mock settings with missing API key
        mock_getattr.side_effect = lambda obj, key, default=None: None if key == 'OPENAI_API_KEY' else default
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("OpenAI API key not configured", str(context.exception))
    
    def test_process_guidelines_with_gpt_empty_guidelines(self):
        """Test GPT processing with empty guidelines."""
        from guideline_ingestion.jobs.tasks import process_guidelines_with_gpt, PermanentProcessingError
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt("")
        
        self.assertIn("Guidelines cannot be empty", str(context.exception))
        
        with self.assertRaises(PermanentProcessingError):
            process_guidelines_with_gpt("   ")
        
        with self.assertRaises(PermanentProcessingError):
            process_guidelines_with_gpt(None)
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_validation_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with validation error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError,
            GPTValidationError
        )
        
        # Mock settings
        mock_getattr.return_value = 'test-value'
        
        # Mock GPT client to raise validation error
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = GPTValidationError("Invalid input format")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("Invalid input", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_rate_limit_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with rate limit error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            TemporaryProcessingError,
            GPTRateLimitError
        )
        
        # Mock settings
        mock_getattr.return_value = 'test-value'
        
        # Mock GPT client to raise rate limit error
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = GPTRateLimitError("Rate limit exceeded")
        
        with self.assertRaises(TemporaryProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("Rate limit exceeded", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_temporary_summarization_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with temporary summarization error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            TemporaryProcessingError,
            SummarizationError
        )
        
        # Mock settings
        mock_getattr.return_value = 'test-value'
        
        # Mock GPT client to raise summarization error with temporary indicators
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = SummarizationError("Connection timeout occurred")
        
        with self.assertRaises(TemporaryProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("Temporary GPT error", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_permanent_summarization_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with permanent summarization error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError,
            SummarizationError
        )
        
        # Mock settings
        mock_getattr.return_value = 'test-value'
        
        # Mock GPT client to raise summarization error without temporary indicators
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = SummarizationError("Invalid model configuration")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("GPT processing failed", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_checklist_generation_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with checklist generation error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError,
            ChecklistGenerationError
        )
        
        # Mock settings
        mock_getattr.return_value = 'test-value'
        
        # Mock GPT client to raise checklist generation error
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = ChecklistGenerationError("Invalid JSON response")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("GPT processing failed", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_client_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with general client error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError,
            GPTClientError
        )
        
        # Mock settings
        mock_getattr.return_value = 'test-value'
        
        # Mock GPT client to raise client error
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = GPTClientError("Client initialization failed")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("GPT client error", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_unexpected_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with unexpected error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError
        )
        
        # Mock settings
        mock_getattr.return_value = 'test-value'
        
        # Mock GPT client to raise unexpected error
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = RuntimeError("Unexpected runtime error")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("Unexpected GPT error", str(context.exception))


class TestErrorCategorizationFunctions(TestCase):
    """Test error categorization and retry logic functions."""
    
    def test_should_retry_error_temporary_indicators(self):
        """Test error categorization for temporary errors that should retry."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        temporary_errors = [
            "Rate limit exceeded",
            "Connection timeout occurred",
            "Network error detected",
            "Server error 503",
            "Service unavailable",
            "Temporary failure",
            "5xx server error"
        ]
        
        for error_message in temporary_errors:
            self.assertTrue(_should_retry_error(error_message), 
                          f"Error '{error_message}' should trigger retry")
    
    def test_should_retry_error_permanent_indicators(self):
        """Test error categorization for permanent errors that should not retry."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        permanent_errors = [
            "Invalid API key",
            "Authentication failed",
            "Authorization denied",
            "Permission denied",
            "Not found error",
            "Bad request format",
            "Invalid input data",
            "Malformed request",
            "4xx client error"
        ]
        
        for error_message in permanent_errors:
            self.assertFalse(_should_retry_error(error_message), 
                           f"Error '{error_message}' should not trigger retry")
    
    def test_should_retry_error_case_insensitive(self):
        """Test error categorization is case insensitive."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        # Test temporary error in different cases
        self.assertTrue(_should_retry_error("RATE LIMIT EXCEEDED"))
        self.assertTrue(_should_retry_error("Rate Limit Exceeded"))
        self.assertTrue(_should_retry_error("rate limit exceeded"))
        
        # Test permanent error in different cases
        self.assertFalse(_should_retry_error("INVALID API KEY"))
        self.assertFalse(_should_retry_error("Invalid Api Key"))
        self.assertFalse(_should_retry_error("invalid api key"))
    
    def test_should_retry_error_unknown_defaults_to_retry(self):
        """Test that unknown errors default to retry (conservative approach)."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        unknown_errors = [
            "Some unknown error occurred",
            "Mysterious failure",
            "Unrecognized error type"
        ]
        
        for error_message in unknown_errors:
            self.assertTrue(_should_retry_error(error_message), 
                          f"Unknown error '{error_message}' should default to retry")
    
    def test_calculate_retry_delay_exponential_backoff(self):
        """Test retry delay calculation with exponential backoff."""
        from guideline_ingestion.jobs.tasks import _calculate_retry_delay
        
        # Test exponential backoff: 60, 120, 240 seconds
        self.assertEqual(_calculate_retry_delay(0), 60)   # First retry: 60s
        self.assertEqual(_calculate_retry_delay(1), 120)  # Second retry: 120s 
        self.assertEqual(_calculate_retry_delay(2), 240)  # Third retry: 240s
    
    def test_calculate_retry_delay_max_limit(self):
        """Test retry delay calculation respects maximum limit."""
        from guideline_ingestion.jobs.tasks import _calculate_retry_delay
        
        # Test that delay caps at 300 seconds (5 minutes)
        self.assertEqual(_calculate_retry_delay(10), 300)  # Should cap at max
        self.assertEqual(_calculate_retry_delay(20), 300)  # Should cap at max


class TestAdvancedJobProcessing(TransactionTestCase):
    """Test advanced job processing scenarios and edge cases."""
    
    def setUp(self):
        """Set up test job."""
        self.job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Test guidelines for advanced processing'}
        )
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_job_database_error_during_status_update(self, mock_gpt_process):
        """Test handling of database errors during job status updates."""
        from guideline_ingestion.jobs.tasks import process_guideline_job
        
        # Mock successful GPT processing
        mock_gpt_process.return_value = {
            'summary': 'Test summary',
            'checklist': []
        }
        
        # Mock database error during job refresh
        with patch.object(Job, 'refresh_from_db', side_effect=Exception("Database connection lost")):
            with self.assertRaises(Exception):
                process_guideline_job(self.job.id, 'Test guidelines')
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_job_job_not_found_during_processing(self, mock_gpt_process):
        """Test handling when job is deleted during processing."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Delete the job before processing
        job_id = self.job.id
        self.job.delete()
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guideline_job(job_id, 'Test guidelines')
        
        self.assertIn("not found", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_job_already_completed(self, mock_gpt_process):
        """Test handling of job that's already completed."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Mark job as completed
        self.job.mark_as_completed({'summary': 'Already done', 'checklist': []})
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guideline_job(self.job.id, 'Test guidelines')
        
        self.assertIn("already finished", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_job_already_failed(self, mock_gpt_process):
        """Test handling of job that's already failed."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Mark job as failed
        self.job.mark_as_failed('Previous failure')
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guideline_job(self.job.id, 'Test guidelines')
        
        self.assertIn("already finished", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_job_retry_count_tracking(self, mock_gpt_process):
        """Test that retry count is properly tracked."""
        from guideline_ingestion.jobs.tasks import process_guideline_job
        
        # Mock temporary error
        mock_gpt_process.side_effect = Exception("Rate limit exceeded")
        
        # Mock the task's retry method to avoid actual retry
        task = process_guideline_job
        with patch.object(task, 'retry', side_effect=Exception("Max retries simulated")):
            try:
                task(self.job.id, 'Test guidelines')
            except:
                pass
        
        # Verify retry count was incremented
        self.job.refresh_from_db()
        self.assertGreater(self.job.retry_count, 0)
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_job_max_retries_exceeded_marking(self, mock_gpt_process):
        """Test job is marked as failed when max retries exceeded."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Set job to max retry count
        self.job.retry_count = 3
        self.job.save()
        
        # Mock persistent error
        mock_gpt_process.side_effect = Exception("Persistent error")
        
        with self.assertRaises(PermanentProcessingError):
            process_guideline_job(self.job.id, 'Test guidelines')
        
        # Verify job was marked as failed
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.FAILED)
        self.assertIn("Max retries exceeded", self.job.error_message)
    
    def test_process_job_database_update_failure_handling(self):
        """Test graceful handling when job status update fails."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Mock database error during job update after processing error
        with patch.object(Job.objects, 'get', side_effect=Exception("Database error")):
            with self.assertRaises(PermanentProcessingError):
                process_guideline_job(self.job.id, 'Test guidelines')


class TestCleanupOldJobsTask(TestCase):
    """Test the cleanup_old_jobs task functionality."""
    
    def setUp(self):
        """Set up test jobs in different states and ages."""
        from datetime import timedelta
        from django.utils import timezone
        
        now = timezone.now()
        
        # Create old completed job (should be cleaned up)
        self.old_completed_job = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Old completed job'},
            created_at=now - timedelta(days=35),
            completed_at=now - timedelta(days=35),
            result={'summary': 'Old summary', 'checklist': []}
        )
        
        # Create old failed job (should be cleaned up)
        self.old_failed_job = Job.objects.create(
            status=JobStatus.FAILED,
            input_data={'guidelines': 'Old failed job'},
            created_at=now - timedelta(days=40),
            completed_at=now - timedelta(days=40),
            error_message='Old error'
        )
        
        # Create recent completed job (should not be cleaned up)
        self.recent_completed_job = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Recent completed job'},
            created_at=now - timedelta(days=10),
            completed_at=now - timedelta(days=10),
            result={'summary': 'Recent summary', 'checklist': []}
        )
        
        # Create old pending job (should not be cleaned up)
        self.old_pending_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Old pending job'},
            created_at=now - timedelta(days=35)
        )
        
        # Create old processing job (should not be cleaned up)
        self.old_processing_job = Job.objects.create(
            status=JobStatus.PROCESSING,
            input_data={'guidelines': 'Old processing job'},
            created_at=now - timedelta(days=35),
            started_at=now - timedelta(days=35)
        )
    
    def test_cleanup_old_jobs_default_retention(self):
        """Test cleanup with default 30-day retention."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        # Execute cleanup with default retention (30 days)
        result = cleanup_old_jobs()
        
        # Verify old completed and failed jobs were deleted
        self.assertFalse(Job.objects.filter(id=self.old_completed_job.id).exists())
        self.assertFalse(Job.objects.filter(id=self.old_failed_job.id).exists())
        
        # Verify recent and non-terminal jobs were kept
        self.assertTrue(Job.objects.filter(id=self.recent_completed_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.old_pending_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.old_processing_job.id).exists())
        
        # Verify return message
        self.assertIn("2 jobs removed", result)
    
    def test_cleanup_old_jobs_custom_retention(self):
        """Test cleanup with custom retention period."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        # Execute cleanup with 50-day retention (should delete nothing)
        result = cleanup_old_jobs(retention_days=50)
        
        # Verify no jobs were deleted
        self.assertTrue(Job.objects.filter(id=self.old_completed_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.old_failed_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.recent_completed_job.id).exists())
        
        # Verify return message
        self.assertIn("0 jobs removed", result)
    
    def test_cleanup_old_jobs_very_short_retention(self):
        """Test cleanup with very short retention period."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        # Execute cleanup with 1-day retention (should delete all terminal jobs)
        result = cleanup_old_jobs(retention_days=1)
        
        # Count expected deletions (completed and failed jobs)
        expected_deletions = 2  # old_completed_job + old_failed_job + recent_completed_job
        
        # Verify terminal jobs were deleted but active jobs remain
        self.assertTrue(Job.objects.filter(id=self.old_pending_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.old_processing_job.id).exists())
        
        # Verify return message indicates deletions
        self.assertIn("jobs removed", result)
    
    def test_cleanup_old_jobs_no_jobs_to_cleanup(self):
        """Test cleanup when no jobs need to be cleaned up."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        # Delete all old jobs first
        Job.objects.filter(
            id__in=[self.old_completed_job.id, self.old_failed_job.id]
        ).delete()
        
        # Execute cleanup
        result = cleanup_old_jobs()
        
        # Verify return message indicates no cleanup
        self.assertIn("0 jobs removed", result)


class TestMonitorJobHealthTask(TestCase):
    """Test the monitor_job_health task functionality."""
    
    def setUp(self):
        """Set up test jobs for health monitoring."""
        from datetime import timedelta
        from django.utils import timezone
        
        # Clear all existing jobs to ensure predictable test environment
        Job.objects.all().delete()
        
        self.now = timezone.now()
        
        # Create stuck job (processing for >30 minutes)
        self.stuck_job = Job.objects.create(
            status=JobStatus.PROCESSING,
            input_data={'guidelines': 'Stuck job'},
            started_at=self.now - timedelta(minutes=45)
        )
        
        # Create recent processing job (not stuck)
        self.recent_processing_job = Job.objects.create(
            status=JobStatus.PROCESSING,
            input_data={'guidelines': 'Recent processing job'},
            started_at=self.now - timedelta(minutes=5)
        )
        
        # Create recent completed jobs
        self.recent_completed_jobs = []
        for i in range(5):
            job = Job.objects.create(
                status=JobStatus.COMPLETED,
                input_data={'guidelines': f'Completed job {i}'},
                created_at=self.now - timedelta(minutes=30),
                started_at=self.now - timedelta(minutes=30),
                completed_at=self.now - timedelta(minutes=25),
                result={'summary': f'Summary {i}', 'checklist': []}
            )
            self.recent_completed_jobs.append(job)
        
        # Create recent failed jobs (need enough to trigger >20% failure rate)
        # With 21 total jobs, need at least 5 failed jobs to get >20% (5/21 = 23.8%)
        self.recent_failed_jobs = []
        for i in range(5):
            job = Job.objects.create(
                status=JobStatus.FAILED,
                input_data={'guidelines': f'Failed job {i}'},
                created_at=self.now - timedelta(minutes=30),
                started_at=self.now - timedelta(minutes=30),
                completed_at=self.now - timedelta(minutes=25),
                error_message=f'Error {i}'
            )
            self.recent_failed_jobs.append(job)
        
        # Create pending jobs for queue backlog test
        self.pending_jobs = []
        for i in range(10):
            job = Job.objects.create(
                status=JobStatus.PENDING,
                input_data={'guidelines': f'Pending job {i}'}
            )
            self.pending_jobs.append(job)
    
    def test_monitor_job_health_detects_stuck_jobs(self):
        """Test health monitoring detects stuck processing jobs."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        result = monitor_job_health()
        
        # Verify stuck job was detected
        self.assertIn("1 stuck jobs detected", result)
        self.assertIn("ALERT", result)
    
    def test_monitor_job_health_no_stuck_jobs(self):
        """Test health monitoring when no jobs are stuck."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Update stuck job to be recent
        self.stuck_job.started_at = self.now - timedelta(minutes=5)
        self.stuck_job.save()
        
        result = monitor_job_health()
        
        # Verify no stuck jobs detected (but other alerts may be present)
        self.assertIn("No stuck jobs detected", result)
        # Don't check for absence of ALERT since other conditions may trigger alerts
    
    def test_monitor_job_health_calculates_failure_rate(self):
        """Test health monitoring calculates failure rate correctly."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        result = monitor_job_health()
        
        # With 1 stuck + 1 recent + 5 completed + 5 failed + 10 pending = 22 total
        # 5 failed out of 22 = 22.7% failure rate, should trigger alert since >20%
        self.assertIn("ALERT: High failure rate", result)
        self.assertIn("22.", result)  # Should contain failure percentage around 22%
    
    def test_monitor_job_health_acceptable_failure_rate(self):
        """Test health monitoring with acceptable failure rate."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Delete two failed jobs to get 3/20 = 15% failure rate (below 20% threshold)
        self.recent_failed_jobs[0].delete()
        self.recent_failed_jobs[1].delete()
        
        result = monitor_job_health()
        
        # Should not trigger failure rate alert
        self.assertNotIn("High failure rate", result)
        failure_rate_line = [line for line in result.split(";") if "Failure rate" in line]
        self.assertTrue(len(failure_rate_line) > 0)
    
    def test_monitor_job_health_queue_backlog_alert(self):
        """Test health monitoring detects large queue backlog."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Create additional pending jobs to exceed threshold (50)
        for i in range(50):
            Job.objects.create(
                status=JobStatus.PENDING,
                input_data={'guidelines': f'Additional pending job {i}'}
            )
        
        result = monitor_job_health()
        
        # Should trigger queue backlog alert
        self.assertIn("ALERT: Large queue backlog", result)
        self.assertIn("60 pending", result)  # 10 original + 50 additional
    
    def test_monitor_job_health_acceptable_queue_backlog(self):
        """Test health monitoring with acceptable queue backlog."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        result = monitor_job_health()
        
        # With 10 pending jobs, should not trigger alert
        self.assertNotIn("Large queue backlog", result)
        self.assertIn("Queue backlog: 10 pending jobs", result)
    
    def test_monitor_job_health_processing_times(self):
        """Test health monitoring calculates processing times."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        result = monitor_job_health()
        
        # All completed jobs have 5-minute processing time (300 seconds)
        # Should trigger slow processing alert (>120s threshold)
        self.assertIn("ALERT: Slow processing", result)
        self.assertIn("avg", result)
        self.assertIn("300.0s", result)
    
    def test_monitor_job_health_slow_processing_alert(self):
        """Test health monitoring detects slow processing."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Update completed jobs to have slow processing time
        for job in self.recent_completed_jobs:
            job.completed_at = job.started_at + timedelta(minutes=10)  # 600 seconds
            job.save()
        
        result = monitor_job_health()
        
        # Should trigger slow processing alert
        self.assertIn("ALERT: Slow processing", result)
    
    def test_monitor_job_health_no_recent_jobs(self):
        """Test health monitoring when no recent jobs exist."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Delete all recent jobs
        Job.objects.filter(
            created_at__gte=self.now - timedelta(hours=1)
        ).delete()
        
        result = monitor_job_health()
        
        # Should handle gracefully
        self.assertIn("No recent jobs to analyze", result)
        self.assertIn("No completed jobs to analyze", result)


class TestGPTProcessingFunction(TestCase):
    """Test process_guidelines_with_gpt function comprehensively."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_guidelines = "Test guidelines with sufficient content for processing."
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    def test_process_guidelines_with_gpt_missing_api_key(self, mock_getattr):
        """Test GPT processing with missing API key."""
        from guideline_ingestion.jobs.tasks import process_guidelines_with_gpt, PermanentProcessingError
        
        # Mock settings to return None for API key
        def mock_settings_get(settings_obj, key, default=None):
            if key == 'OPENAI_API_KEY':
                return None
            return 'test-value'
        
        mock_getattr.side_effect = mock_settings_get
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("OpenAI API key not configured", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_client_configuration(self, mock_gpt_client_class, mock_getattr):
        """Test GPT client is configured correctly."""
        from guideline_ingestion.jobs.tasks import process_guidelines_with_gpt
        
        # Mock settings values
        settings_map = {
            'OPENAI_API_KEY': 'test-api-key',
            'OPENAI_MODEL': 'gpt-4',
            'OPENAI_MAX_TOKENS': 2000,
            'OPENAI_TEMPERATURE': 0.1,
            'OPENAI_RATE_LIMIT_REQUESTS': 60,
            'OPENAI_RATE_LIMIT_WINDOW': 60
        }
        mock_getattr.side_effect = lambda settings_obj, key, default=None: settings_map.get(key, default)
        
        # Mock client
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.return_value = {"summary": "test", "checklist": []}
        
        process_guidelines_with_gpt(self.valid_guidelines)
        
        # Verify client was created with correct parameters
        mock_gpt_client_class.assert_called_once_with(
            api_key='test-api-key',
            model='gpt-4',
            max_tokens=2000,
            temperature=0.1,
            rate_limit_requests=60,
            rate_limit_window=60
        )
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_summarization_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with summarization error (temporary)."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            TemporaryProcessingError,
            SummarizationError
        )
        
        mock_getattr.return_value = 'test-value'
        
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = SummarizationError("Rate limit exceeded")
        
        with self.assertRaises(TemporaryProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("Rate limit exceeded", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_permanent_summarization_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with permanent summarization error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError,
            SummarizationError
        )
        
        mock_getattr.return_value = 'test-value'
        
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = SummarizationError("Invalid format")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("GPT processing failed", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_checklist_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with checklist generation error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError,
            ChecklistGenerationError
        )
        
        mock_getattr.return_value = 'test-value'
        
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = ChecklistGenerationError("Validation failed")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("GPT processing failed", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_generic_client_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with generic client error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError,
            GPTClientError
        )
        
        mock_getattr.return_value = 'test-value'
        
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = GPTClientError("Client initialization failed")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("GPT client error", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.getattr')
    @patch('guideline_ingestion.jobs.tasks.GPTClient')
    def test_process_guidelines_with_gpt_unexpected_error(self, mock_gpt_client_class, mock_getattr):
        """Test GPT processing with unexpected error."""
        from guideline_ingestion.jobs.tasks import (
            process_guidelines_with_gpt, 
            PermanentProcessingError
        )
        
        mock_getattr.return_value = 'test-value'
        
        mock_client = MagicMock()
        mock_gpt_client_class.return_value = mock_client
        mock_client.process_guidelines.side_effect = RuntimeError("Unexpected system error")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guidelines_with_gpt(self.valid_guidelines)
        
        self.assertIn("Unexpected GPT error", str(context.exception))


class TestErrorCategorizationFunctions(TestCase):
    """Test error categorization and retry logic functions."""
    
    def test_should_retry_error_temporary_indicators(self):
        """Test error categorization identifies temporary errors."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        temporary_errors = [
            "Rate limit exceeded",
            "Connection timeout",
            "Network error occurred",
            "Server error 5xx",
            "Service unavailable",
            "Temporary failure",
            "Please retry request"
        ]
        
        for error_msg in temporary_errors:
            with self.subTest(error=error_msg):
                self.assertTrue(_should_retry_error(error_msg))
    
    def test_should_retry_error_permanent_indicators(self):
        """Test error categorization identifies permanent errors."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        permanent_errors = [
            "Invalid API key",
            "Authentication failed",
            "Authorization denied",
            "Permission denied",
            "Resource not found",
            "Bad request format",
            "Invalid input data",
            "Malformed request",
            "Client error 4xx"
        ]
        
        for error_msg in permanent_errors:
            with self.subTest(error=error_msg):
                self.assertFalse(_should_retry_error(error_msg))
    
    def test_should_retry_error_unknown_defaults_to_retry(self):
        """Test unknown errors default to retry (conservative approach)."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        unknown_errors = [
            "Some unexpected error",
            "Custom application error",
            "Undefined system failure"
        ]
        
        for error_msg in unknown_errors:
            with self.subTest(error=error_msg):
                self.assertTrue(_should_retry_error(error_msg))
    
    def test_should_retry_error_case_insensitive(self):
        """Test error categorization is case insensitive."""
        from guideline_ingestion.jobs.tasks import _should_retry_error
        
        # Test both cases for the same error type
        self.assertTrue(_should_retry_error("RATE LIMIT EXCEEDED"))
        self.assertTrue(_should_retry_error("rate limit exceeded"))
        
        self.assertFalse(_should_retry_error("INVALID API KEY"))
        self.assertFalse(_should_retry_error("invalid api key"))
    
    def test_calculate_retry_delay_exponential_backoff(self):
        """Test retry delay calculation uses exponential backoff."""
        from guideline_ingestion.jobs.tasks import _calculate_retry_delay
        
        # Test exponential backoff pattern: 60, 120, 240 seconds
        self.assertEqual(_calculate_retry_delay(1), 120)  # 60 * 2^1
        self.assertEqual(_calculate_retry_delay(2), 240)  # 60 * 2^2
        self.assertEqual(_calculate_retry_delay(3), 300)  # Capped at max_delay
    
    def test_calculate_retry_delay_max_cap(self):
        """Test retry delay is capped at maximum value."""
        from guideline_ingestion.jobs.tasks import _calculate_retry_delay
        
        # Test large retry counts are capped
        self.assertEqual(_calculate_retry_delay(10), 300)  # Max 5 minutes
        self.assertEqual(_calculate_retry_delay(100), 300)  # Max 5 minutes
    
    def test_calculate_retry_delay_zero_retry(self):
        """Test retry delay for first retry."""
        from guideline_ingestion.jobs.tasks import _calculate_retry_delay
        
        # First retry should be base delay * 2^0 = 60 seconds
        self.assertEqual(_calculate_retry_delay(0), 60)


class TestAdvancedJobProcessing(TransactionTestCase):
    """Test advanced job processing scenarios with database transactions."""
    
    def setUp(self):
        """Set up test data."""
        self.job = Job.objects.create(
            input_data={'guidelines': 'Test guidelines for processing', 'priority': 'medium'}
        )
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_guideline_job_database_error_during_completion(self, mock_gpt_process):
        """Test job processing handles database errors during completion."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        mock_gpt_process.return_value = {"summary": "test", "checklist": []}
        
        # Mock job.mark_as_completed to raise a database error
        with patch.object(Job, 'mark_as_completed') as mock_complete:
            mock_complete.side_effect = DatabaseError("Connection lost")
            
            with self.assertRaises(PermanentProcessingError):
                process_guideline_job(self.job.id, self.job.input_data['guidelines'])
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_guideline_job_retry_count_tracking(self, mock_gpt_process):
        """Test job processing properly tracks retry counts."""
        from guideline_ingestion.jobs.tasks import process_guideline_job
        
        # Mock to raise temporary error
        mock_gpt_process.side_effect = Exception("Rate limit exceeded")
        
        # Mock _should_retry_error to return True
        with patch('guideline_ingestion.jobs.tasks._should_retry_error') as mock_should_retry:
            mock_should_retry.return_value = True
            
            try:
                process_guideline_job(self.job.id, self.job.input_data['guidelines'])
            except:
                pass  # Expected to fail
            
            # Check retry count was incremented
            self.job.refresh_from_db()
            self.assertEqual(self.job.retry_count, 1)
    
    def test_process_guideline_job_concurrent_processing_detection(self):
        """Test job processing detects concurrent processing attempts."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Mark job as already processing
        self.job.mark_as_processing()
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guideline_job(self.job.id, self.job.input_data['guidelines'])
        
        self.assertIn("already being processed", str(context.exception))
    
    def test_process_guideline_job_completed_job_detection(self):
        """Test job processing detects already completed jobs."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Mark job as completed
        self.job.mark_as_completed({"summary": "test", "checklist": []})
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guideline_job(self.job.id, self.job.input_data['guidelines'])
        
        self.assertIn("already finished", str(context.exception))
    
    def test_process_guideline_job_failed_job_detection(self):
        """Test job processing detects already failed jobs."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Mark job as failed
        self.job.mark_as_failed("Previous failure")
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guideline_job(self.job.id, self.job.input_data['guidelines'])
        
        self.assertIn("already finished", str(context.exception))
    
    def test_process_guideline_job_nonexistent_job(self):
        """Test job processing handles nonexistent job IDs."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        nonexistent_id = 99999
        
        with self.assertRaises(PermanentProcessingError) as context:
            process_guideline_job(nonexistent_id, "test guidelines")
        
        self.assertIn("not found", str(context.exception))
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_process_guideline_job_max_retries_handling(self, mock_gpt_process):
        """Test job processing handles max retries exceeded."""
        from guideline_ingestion.jobs.tasks import process_guideline_job, PermanentProcessingError
        
        # Set job to have 3 retries already
        self.job.retry_count = 3
        self.job.save()
        
        mock_gpt_process.side_effect = Exception("Rate limit exceeded")
        
        with patch('guideline_ingestion.jobs.tasks._should_retry_error') as mock_should_retry:
            mock_should_retry.return_value = True
            
            with self.assertRaises(PermanentProcessingError) as context:
                process_guideline_job(self.job.id, self.job.input_data['guidelines'])
            
            self.assertIn("Max retries exceeded", str(context.exception))
            
            # Verify job was marked as failed
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, JobStatus.FAILED)


class TestCleanupAndMonitoringTasks(TestCase):
    """Test cleanup and monitoring task functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.now = timezone.now()
        
        # Create old jobs for cleanup testing
        self.old_completed_job = Job.objects.create(
            input_data={'guidelines': 'Old completed job'},
            status=JobStatus.COMPLETED,
            completed_at=self.now - timedelta(days=35),
            started_at=self.now - timedelta(days=35),
            result={"summary": "test", "checklist": []}
        )
        
        self.old_failed_job = Job.objects.create(
            input_data={'guidelines': 'Old failed job'},
            status=JobStatus.FAILED,
            completed_at=self.now - timedelta(days=40),
            error_message="Test error"
        )
        
        # Create recent jobs that should not be cleaned up
        self.recent_completed_job = Job.objects.create(
            input_data={'guidelines': 'Recent completed job'},
            status=JobStatus.COMPLETED,
            completed_at=self.now - timedelta(days=10),
            result={"summary": "test", "checklist": []}
        )
        
        # Create processing and pending jobs that should never be cleaned up
        self.processing_job = Job.objects.create(
            input_data={'guidelines': 'Processing job'},
            status=JobStatus.PROCESSING,
            started_at=self.now - timedelta(days=50)
        )
        
        self.pending_job = Job.objects.create(
            input_data={'guidelines': 'Pending job'},
            status=JobStatus.PENDING,
            created_at=self.now - timedelta(days=50)
        )
    
    def test_cleanup_old_jobs_default_retention(self):
        """Test cleanup task with default 30-day retention."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        initial_count = Job.objects.count()
        result = cleanup_old_jobs()
        
        # Should remove 2 old jobs (completed and failed)
        final_count = Job.objects.count()
        self.assertEqual(initial_count - final_count, 2)
        
        # Check specific jobs
        self.assertFalse(Job.objects.filter(id=self.old_completed_job.id).exists())
        self.assertFalse(Job.objects.filter(id=self.old_failed_job.id).exists())
        
        # Check recent and active jobs remain
        self.assertTrue(Job.objects.filter(id=self.recent_completed_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.processing_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.pending_job.id).exists())
        
        self.assertIn("2 jobs removed", result)
    
    def test_cleanup_old_jobs_custom_retention(self):
        """Test cleanup task with custom retention period."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        # Use 15-day retention (should clean old jobs but not recent ones)
        result = cleanup_old_jobs(retention_days=15)
        
        # Should remove 2 old jobs (old completed + old failed)
        self.assertFalse(Job.objects.filter(id=self.old_completed_job.id).exists())
        self.assertFalse(Job.objects.filter(id=self.old_failed_job.id).exists())
        # Recent completed job (10 days old) should still exist as it's not older than 15 days
        self.assertTrue(Job.objects.filter(id=self.recent_completed_job.id).exists())
        
        # Active jobs still remain
        self.assertTrue(Job.objects.filter(id=self.processing_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.pending_job.id).exists())
        
        # Should report removing 2 jobs
        self.assertIn("2 jobs removed", result)
    
    def test_cleanup_old_jobs_no_jobs_to_clean(self):
        """Test cleanup task when no old jobs exist."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        # Delete old jobs manually
        Job.objects.filter(
            id__in=[self.old_completed_job.id, self.old_failed_job.id]
        ).delete()
        
        result = cleanup_old_jobs()
        
        self.assertIn("0 jobs removed", result)
    
    def test_cleanup_old_jobs_preserves_active_statuses(self):
        """Test cleanup task never removes pending or processing jobs."""
        from guideline_ingestion.jobs.tasks import cleanup_old_jobs
        
        # Use very short retention to test status preservation
        result = cleanup_old_jobs(retention_days=1)
        
        # Active jobs should never be cleaned regardless of age
        self.assertTrue(Job.objects.filter(id=self.processing_job.id).exists())
        self.assertTrue(Job.objects.filter(id=self.pending_job.id).exists())
    
    def test_monitor_job_health_no_alerts(self):
        """Test health monitoring with healthy system state."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Clean slate - remove test jobs to avoid interference
        Job.objects.all().delete()
        
        # Create healthy job state
        Job.objects.create(
            input_data={'guidelines': 'Recent completed job'},
            status=JobStatus.COMPLETED,
            created_at=self.now - timedelta(minutes=30),
            started_at=self.now - timedelta(minutes=30),
            completed_at=self.now - timedelta(minutes=28),  # 2 minute processing
            result={"summary": "test", "checklist": []}
        )
        
        result = monitor_job_health()
        
        # Should report healthy state
        self.assertNotIn("ALERT", result)
        self.assertIn("No stuck jobs detected", result)
        self.assertIn("Queue backlog: 0 pending jobs", result)
    
    def test_monitor_job_health_stuck_jobs_detection(self):
        """Test health monitoring detects stuck jobs."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Clean slate to avoid interference from other tests
        Job.objects.all().delete()
        
        # Create stuck job (processing for >30 minutes)
        stuck_job = Job.objects.create(
            input_data={'guidelines': 'Stuck job'},
            status=JobStatus.PROCESSING,
            started_at=self.now - timedelta(minutes=45)
        )
        
        result = monitor_job_health()
        
        self.assertIn("ALERT: 1 stuck jobs detected", result)
    
    def test_monitor_job_health_high_failure_rate(self):
        """Test health monitoring detects high failure rates."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Clean slate
        Job.objects.all().delete()
        
        # Create high failure rate scenario (80% failures)
        for i in range(8):
            Job.objects.create(
                input_data={'guidelines': f'Failed job {i}'},
                status=JobStatus.FAILED,
                created_at=self.now - timedelta(minutes=30),
                error_message="Test failure"
            )
        
        for i in range(2):
            Job.objects.create(
                input_data={'guidelines': f'Completed job {i}'},
                status=JobStatus.COMPLETED,
                created_at=self.now - timedelta(minutes=30),
                result={"summary": "test", "checklist": []}
            )
        
        result = monitor_job_health()
        
        self.assertIn("ALERT: High failure rate", result)
        self.assertIn("80.0%", result)
    
    def test_monitor_job_health_large_queue_backlog(self):
        """Test health monitoring detects large queue backlogs."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Clean slate
        Job.objects.all().delete()
        
        # Create large backlog (>50 pending jobs)
        for i in range(60):
            Job.objects.create(
                input_data={'guidelines': f'Pending job {i}'},
                status=JobStatus.PENDING
            )
        
        result = monitor_job_health()
        
        self.assertIn("ALERT: Large queue backlog (60 pending)", result)
    
    def test_monitor_job_health_slow_processing_detection(self):
        """Test health monitoring detects slow processing times."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        # Clean slate
        Job.objects.all().delete()
        
        # Create slow processing jobs (>2 minutes average)
        for i in range(3):
            job = Job.objects.create(
                input_data={'guidelines': f'Slow job {i}'},
                status=JobStatus.COMPLETED,
                created_at=self.now - timedelta(hours=1),
                started_at=self.now - timedelta(minutes=10),
                completed_at=self.now - timedelta(minutes=5),  # 5 minute processing
                result={"summary": "test", "checklist": []}
            )
        
        result = monitor_job_health()
        
        self.assertIn("ALERT: Slow processing", result)
    
    def test_monitor_job_health_comprehensive_report(self):
        """Test health monitoring provides comprehensive reporting."""
        from guideline_ingestion.jobs.tasks import monitor_job_health
        
        result = monitor_job_health()
        
        # Should include all monitoring categories
        self.assertIn("stuck jobs", result.lower())
        self.assertIn("failure rate", result.lower())
        self.assertIn("queue backlog", result.lower())
        self.assertIn("processing times", result.lower())