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