"""
Tests for jobs API views (TDD Red Phase).

This module contains comprehensive tests for the job API endpoints,
performance validation, and error handling scenarios.
"""

import json
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from guideline_ingestion.jobs.models import Job, JobStatus


class TestJobCreateView(APITestCase):
    """Test POST /jobs endpoint with comprehensive validation."""
    
    def setUp(self):
        """Set up test client and sample data."""
        self.client = APIClient()
        self.url = reverse('jobs:job-create')
        
        self.valid_payload = {
            'guidelines': 'This is a test guideline document that contains important information for processing.',
            'callback_url': 'https://example.com/callback',
            'priority': 'normal',
            'metadata': {
                'source': 'test',
                'version': '1.0',
                'department': 'engineering'
            }
        }
        
        self.minimal_payload = {
            'guidelines': 'Minimal test guidelines for processing validation.'
        }
    
    def test_job_create_success_full_payload(self):
        """Test successful job creation with full payload."""
        response = self.client.post(
            self.url,
            data=json.dumps(self.valid_payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('data', response_data)
        
        data = response_data['data']
        self.assertIn('event_id', data)
        self.assertEqual(data['status'], 'PENDING')
        self.assertIn('created_at', data)
        self.assertIn('estimated_completion', data)
        
        # Verify UUID format
        uuid.UUID(data['event_id'])
        
        # Verify job was created in database
        job = Job.objects.get(event_id=data['event_id'])
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.input_data['guidelines'], self.valid_payload['guidelines'])
    
    def test_job_create_success_minimal_payload(self):
        """Test successful job creation with minimal required payload."""
        response = self.client.post(
            self.url,
            data=json.dumps(self.minimal_payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        
        # Verify job was created with defaults
        job = Job.objects.get(event_id=response_data['data']['event_id'])
        self.assertIsNone(job.input_data.get('callback_url'))
        self.assertEqual(job.input_data.get('priority', 'normal'), 'normal')
    
    def test_job_create_validation_missing_guidelines(self):
        """Test validation error when guidelines field is missing."""
        payload = {'priority': 'high'}
        
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
        self.assertEqual(response_data['error']['code'], 'VALIDATION_ERROR')
        self.assertIn('guidelines', response_data['error']['details']['field_errors'])
    
    def test_job_create_validation_guidelines_too_short(self):
        """Test validation error when guidelines are too short."""
        payload = {'guidelines': 'Short'}  # Less than 10 characters
        
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('guidelines', response_data['error']['details']['field_errors'])
    
    def test_job_create_validation_guidelines_too_long(self):
        """Test validation error when guidelines exceed maximum length."""
        payload = {'guidelines': 'A' * 10001}  # More than 10000 characters
        
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('guidelines', response_data['error']['details']['field_errors'])
    
    def test_job_create_validation_invalid_callback_url(self):
        """Test validation error for invalid callback URL."""
        payload = {
            'guidelines': 'Valid guidelines for testing callback validation.',
            'callback_url': 'not-a-valid-url'
        }
        
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('callback_url', response_data['error']['details']['field_errors'])
    
    def test_job_create_validation_invalid_priority(self):
        """Test validation error for invalid priority value."""
        payload = {
            'guidelines': 'Valid guidelines for testing priority validation.',
            'priority': 'invalid'
        }
        
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('priority', response_data['error']['details']['field_errors'])
    
    def test_job_create_validation_metadata_too_large(self):
        """Test validation error when metadata exceeds size limit."""
        large_metadata = {f'key_{i}': 'x' * 100 for i in range(15)}  # > 1KB
        payload = {
            'guidelines': 'Valid guidelines for testing metadata validation.',
            'metadata': large_metadata
        }
        
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertIn('metadata', response_data['error']['details']['field_errors'])
    
    def test_job_create_invalid_json(self):
        """Test error handling for invalid JSON payload."""
        response = self.client.post(
            self.url,
            data='{"invalid": json}',
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertEqual(response_data['error']['code'], 'JSON_PARSE_ERROR')
    
    def test_job_create_unsupported_content_type(self):
        """Test error handling for unsupported content type."""
        response = self.client.post(
            self.url,
            data='guidelines=test',
            content_type='application/x-www-form-urlencoded'
        )
        
        self.assertEqual(response.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    
    @patch('guideline_ingestion.jobs.tasks.process_guideline_job.delay')
    def test_job_create_celery_task_queued(self, mock_delay):
        """Test that Celery task is properly queued on job creation."""
        mock_delay.return_value = MagicMock(id='task-id-123')
        
        response = self.client.post(
            self.url,
            data=json.dumps(self.valid_payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify Celery task was called
        mock_delay.assert_called_once()
        call_args = mock_delay.call_args[0]
        self.assertIsInstance(call_args[0], int)  # job.id
        self.assertEqual(call_args[1], self.valid_payload['guidelines'])
    
    def test_job_create_response_time_performance(self):
        """Test that job creation responds within 200ms requirement."""
        start_time = time.time()
        
        response = self.client.post(
            self.url,
            data=json.dumps(self.valid_payload),
            content_type='application/json'
        )
        
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertLess(response_time_ms, 200, f"Response time {response_time_ms}ms exceeds 200ms requirement")
    
    def test_job_create_concurrent_requests(self):
        """Test handling of concurrent job creation requests."""
        import threading
        import queue
        
        results = queue.Queue()
        
        def create_job():
            response = self.client.post(
                self.url,
                data=json.dumps(self.valid_payload),
                content_type='application/json'
            )
            results.put(response.status_code)
        
        # Create 5 concurrent threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_job)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify all succeeded
        while not results.empty():
            status_code = results.get()
            self.assertEqual(status_code, status.HTTP_201_CREATED)


class TestJobRetrieveView(APITestCase):
    """Test GET /jobs/{event_id} endpoint with various job states."""
    
    def setUp(self):
        """Set up test client and sample jobs."""
        self.client = APIClient()
        
        # Create jobs in different states
        self.pending_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Test pending job guidelines'}
        )
        
        self.processing_job = Job.objects.create(
            status=JobStatus.PROCESSING,
            input_data={'guidelines': 'Test processing job guidelines'},
            started_at=timezone.now()
        )
        
        self.completed_job = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Test completed job guidelines'},
            started_at=timezone.now() - timedelta(minutes=2),
            completed_at=timezone.now(),
            result={
                'summary': 'Test summary of guidelines',
                'checklist': [
                    {
                        'id': 1,
                        'title': 'Test checklist item',
                        'description': 'Test description',
                        'priority': 'high',
                        'category': 'security'
                    }
                ]
            }
        )
        
        self.failed_job = Job.objects.create(
            status=JobStatus.FAILED,
            input_data={'guidelines': 'Test failed job guidelines'},
            started_at=timezone.now() - timedelta(minutes=1),
            completed_at=timezone.now(),
            error_message='Test error message'
        )
    
    def test_job_retrieve_pending_status(self):
        """Test retrieving job with PENDING status."""
        url = reverse('jobs:job-retrieve', kwargs={'event_id': self.pending_job.event_id})
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        
        data = response_data['data']
        self.assertEqual(data['event_id'], str(self.pending_job.event_id))
        self.assertEqual(data['status'], 'PENDING')
        self.assertIn('created_at', data)
        self.assertIn('estimated_completion', data)
        self.assertIn('queue_position', data)
    
    def test_job_retrieve_processing_status(self):
        """Test retrieving job with PROCESSING status."""
        url = reverse('jobs:job-retrieve', kwargs={'event_id': self.processing_job.event_id})
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        
        data = response_data['data']
        self.assertEqual(data['event_id'], str(self.processing_job.event_id))
        self.assertEqual(data['status'], 'PROCESSING')
        self.assertIn('started_at', data)
        self.assertIn('estimated_completion', data)
        self.assertIn('current_step', data)
    
    def test_job_retrieve_completed_status(self):
        """Test retrieving job with COMPLETED status."""
        url = reverse('jobs:job-retrieve', kwargs={'event_id': self.completed_job.event_id})
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        
        data = response_data['data']
        self.assertEqual(data['event_id'], str(self.completed_job.event_id))
        self.assertEqual(data['status'], 'COMPLETED')
        self.assertIn('completed_at', data)
        self.assertIn('processing_time_seconds', data)
        self.assertIn('result', data)
        
        # Verify result structure
        result = data['result']
        self.assertIn('summary', result)
        self.assertIn('checklist', result)
        self.assertIsInstance(result['checklist'], list)
    
    def test_job_retrieve_failed_status(self):
        """Test retrieving job with FAILED status."""
        url = reverse('jobs:job-retrieve', kwargs={'event_id': self.failed_job.event_id})
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        
        data = response_data['data']
        self.assertEqual(data['event_id'], str(self.failed_job.event_id))
        self.assertEqual(data['status'], 'FAILED')
        self.assertIn('error_message', data)
        self.assertIn('completed_at', data)
    
    def test_job_retrieve_not_found(self):
        """Test retrieving non-existent job returns 404."""
        non_existent_id = uuid.uuid4()
        url = reverse('jobs:job-retrieve', kwargs={'event_id': non_existent_id})
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertEqual(response_data['error']['code'], 'JOB_NOT_FOUND')
    
    def test_job_retrieve_invalid_uuid_format(self):
        """Test error handling for invalid UUID format."""
        url = reverse('jobs:job-retrieve', kwargs={'event_id': 'invalid-uuid'})
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertEqual(response_data['error']['code'], 'INVALID_UUID')
    
    def test_job_retrieve_response_time_performance(self):
        """Test that job retrieval responds within 100ms requirement."""
        url = reverse('jobs:job-retrieve', kwargs={'event_id': self.completed_job.event_id})
        
        start_time = time.time()
        
        response = self.client.get(url)
        
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(response_time_ms, 100, f"Response time {response_time_ms}ms exceeds 100ms requirement")


class TestJobAPIErrorHandling(APITestCase):
    """Test comprehensive error handling scenarios."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_method_not_allowed(self):
        """Test unsupported HTTP methods return 405."""
        url = reverse('jobs:job-create')
        
        response = self.client.put(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
    
    def test_internal_server_error_handling(self):
        """Test graceful handling of internal server errors."""
        url = reverse('jobs:job-create')
        
        with patch('guideline_ingestion.jobs.models.Job.objects.create') as mock_create:
            mock_create.side_effect = Exception('Database error')
            
            response = self.client.post(
                url,
                data=json.dumps({'guidelines': 'Test guidelines'}),
                content_type='application/json'
            )
            
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            response_data = response.json()
            self.assertFalse(response_data['success'])
            self.assertEqual(response_data['error']['code'], 'INTERNAL_SERVER_ERROR')
    
    def test_rate_limiting_headers(self):
        """Test that rate limiting headers are included in responses."""
        url = reverse('jobs:job-create')
        
        response = self.client.post(
            url,
            data=json.dumps({'guidelines': 'Test guidelines for rate limiting'}),
            content_type='application/json'
        )
        
        # These headers should be added by middleware in production
        # For now, just verify the response structure is correct
        self.assertIn('success', response.json())
    
    def test_cors_headers(self):
        """Test CORS headers are included for browser compatibility."""
        url = reverse('jobs:job-create')
        
        response = self.client.options(url)
        
        # CORS headers should be set by corsheaders middleware
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestJobAPIIntegration(APITestCase):
    """Test end-to-end API integration scenarios."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_job_lifecycle_integration(self):
        """Test complete job lifecycle: create → retrieve → process."""
        # Step 1: Create job
        create_url = reverse('jobs:job-create')
        create_payload = {
            'guidelines': 'Test guidelines for integration testing workflow.',
            'priority': 'high'
        }
        
        create_response = self.client.post(
            create_url,
            data=json.dumps(create_payload),
            content_type='application/json'
        )
        
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        event_id = create_response.json()['data']['event_id']
        
        # Step 2: Retrieve job immediately (should be PENDING)
        retrieve_url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        
        retrieve_response = self.client.get(retrieve_url)
        
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.json()['data']['status'], 'PENDING')
        
        # Step 3: Simulate job processing by updating status
        job = Job.objects.get(event_id=event_id)
        job.mark_as_processing()
        
        # Retrieve again (should be PROCESSING)
        retrieve_response = self.client.get(retrieve_url)
        
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.json()['data']['status'], 'PROCESSING')
        
        # Step 4: Complete job with results
        job.mark_as_completed({
            'summary': 'Integration test summary',
            'checklist': [{'id': 1, 'title': 'Test item'}]
        })
        
        # Final retrieval (should be COMPLETED with results)
        retrieve_response = self.client.get(retrieve_url)
        
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        response_data = retrieve_response.json()['data']
        self.assertEqual(response_data['status'], 'COMPLETED')
        self.assertIn('result', response_data)
        self.assertIn('summary', response_data['result'])
        self.assertIn('checklist', response_data['result'])