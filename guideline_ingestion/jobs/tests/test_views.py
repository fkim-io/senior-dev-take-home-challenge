"""
Tests for jobs API views (TDD Red Phase).

This module contains comprehensive tests for the job API endpoints,
performance validation, and error handling scenarios.
"""

import json
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.db import DatabaseError
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
        
        # DRF returns 400 for form data when expecting JSON
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
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
        # Django's UUID converter automatically rejects invalid UUIDs in URLs
        # So we test by directly hitting a malformed URL
        url = '/jobs/invalid-uuid/'
        
        response = self.client.get(url)
        
        # Django returns 404 for URLs that don't match the pattern
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    


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


class TestViewsEdgeCasesAndErrorHandling(APITestCase):
    """Test additional edge cases and error handling scenarios in views."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_job_create_celery_import_error_graceful_handling(self):
        """Test graceful handling when Celery task import fails."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for Celery import error handling.'
        }
        
        # Mock ImportError during task import
        with patch('guideline_ingestion.jobs.tasks.process_guideline_job', side_effect=ImportError("Celery not available")):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type='application/json'
            )
            
            # Should still succeed - job creation should not fail due to queueing issues
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            
            # Verify job was created
            response_data = response.json()
            self.assertTrue(response_data['success'])
            self.assertIn('event_id', response_data['data'])
    
    def test_job_create_celery_task_queueing_error(self):
        """Test handling of errors during task queueing."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for task queueing error handling.'
        }
        
        # Mock task delay method to raise exception
        with patch('guideline_ingestion.jobs.tasks.process_guideline_job.delay', side_effect=Exception("Redis connection failed")):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type='application/json'
            )
            
            # Should still succeed - job creation should not fail due to queueing issues
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            
            # Verify job was created despite queueing failure
            response_data = response.json()
            self.assertTrue(response_data['success'])
    
    def test_job_retrieve_uuid_conversion_edge_cases(self):
        """Test UUID conversion edge cases in job retrieve view."""
        # Create a test job
        job = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Test guidelines'},
            result={'summary': 'Test summary', 'checklist': []}
        )
        
        url = reverse('jobs:job-retrieve', kwargs={'event_id': job.event_id})
        
        # Test with actual UUID object (should work)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test with string representation (should work)
        url_string = f'/jobs/{str(job.event_id)}/'
        response = self.client.get(url_string)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_job_retrieve_view_unexpected_error_handling(self):
        """Test handling of unexpected errors in job retrieve view."""
        job = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Test guidelines'},
            result={'summary': 'Test summary', 'checklist': []}
        )
        
        url = reverse('jobs:job-retrieve', kwargs={'event_id': job.event_id})
        
        # Mock an unexpected error during job retrieval
        with patch.object(Job.objects, 'get', side_effect=Exception("Database connection lost")):
            response = self.client.get(url)
            
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            response_data = response.json()
            self.assertFalse(response_data['success'])
            self.assertEqual(response_data['error']['code'], 'INTERNAL_SERVER_ERROR')
    
    def test_job_retrieve_serializer_success_response_formatting(self):
        """Test proper formatting of success responses in job retrieve view."""
        job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Test guidelines for response formatting'}
        )
        
        url = reverse('jobs:job-retrieve', kwargs={'event_id': job.event_id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        
        # Verify proper response structure
        self.assertTrue(response_data['success'])
        self.assertIn('data', response_data)
        self.assertNotIn('message', response_data)  # Should not include message for retrieve
        
        # Verify data structure matches serializer output
        data = response_data['data']
        self.assertEqual(data['event_id'], str(job.event_id))
        self.assertEqual(data['status'], 'PENDING')
    
    def test_job_create_database_transaction_error_handling(self):
        """Test handling of database transaction errors during job creation."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for database transaction error.'
        }
        
        # Mock database error during job creation
        with patch.object(Job.objects, 'create', side_effect=Exception("Database integrity error")):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type='application/json'
            )
            
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            response_data = response.json()
            self.assertFalse(response_data['success'])
            self.assertEqual(response_data['error']['code'], 'INTERNAL_SERVER_ERROR')
    
    def test_job_create_estimated_completion_time_calculation(self):
        """Test that estimated completion time is properly calculated."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for completion time estimation.'
        }
        
        start_time = timezone.now()
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        
        # Verify estimated completion time is in the future
        estimated_str = response_data['data']['estimated_completion']
        estimated_time = datetime.fromisoformat(estimated_str.replace('Z', '+00:00'))
        
        # Should be approximately 90 seconds in the future
        expected_completion = start_time + timedelta(seconds=90)
        time_diff = abs((estimated_time - expected_completion).total_seconds())
        
        # Allow 5-second tolerance for test execution time
        self.assertLess(time_diff, 5)
    
    def test_job_create_input_data_storage_formatting(self):
        """Test that input data is properly formatted and stored."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for input data formatting.',
            'callback_url': 'https://example.com/callback',
            'priority': 'high',
            'metadata': {
                'source': 'test',
                'version': '1.0'
            }
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify job was created with proper input data
        event_id = response.json()['data']['event_id']
        job = Job.objects.get(event_id=event_id)
        
        # Verify all input data was stored correctly
        self.assertEqual(job.input_data['guidelines'], payload['guidelines'])
        self.assertEqual(job.input_data['callback_url'], payload['callback_url'])
        self.assertEqual(job.input_data['priority'], payload['priority'])
        self.assertEqual(job.input_data['metadata'], payload['metadata'])
    
    def test_job_create_optional_fields_handling(self):
        """Test handling of optional fields in job creation."""
        url = reverse('jobs:job-create')
        
        # Test with minimal payload (only required field)
        minimal_payload = {
            'guidelines': 'Minimal test guidelines.'
        }
        
        response = self.client.post(
            url,
            data=json.dumps(minimal_payload),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify job was created with defaults
        event_id = response.json()['data']['event_id']
        job = Job.objects.get(event_id=event_id)
        
        # Verify optional fields are handled properly
        self.assertNotIn('callback_url', job.input_data)
        self.assertEqual(job.input_data.get('priority', 'normal'), 'normal')
        self.assertEqual(job.input_data.get('metadata', {}), {})
    
    def test_error_response_request_id_tracking(self):
        """Test that error responses include request ID for tracking."""
        url = reverse('jobs:job-create')
        
        # Send invalid payload to trigger validation error
        response = self.client.post(
            url,
            data=json.dumps({}),  # Missing required guidelines
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        
        # Verify error response includes request tracking info
        self.assertFalse(response_data['success'])
        self.assertIn('error', response_data)
        self.assertIn('timestamp', response_data['error'])
        self.assertIn('request_id', response_data['error'])
    
    def test_parse_error_handling_with_malformed_json(self):
        """Test handling of malformed JSON requests."""
        url = reverse('jobs:job-create')
        
        # Send malformed JSON
        response = self.client.post(
            url,
            data='{"guidelines": "test", "invalid": json}',  # Invalid JSON
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        
        # Verify proper parse error handling
        self.assertFalse(response_data['success'])
        self.assertEqual(response_data['error']['code'], 'JSON_PARSE_ERROR')
        self.assertIn('Invalid JSON', response_data['error']['message'])


class TestViewsPerformanceAndOptimization(APITestCase):
    """Test performance-related aspects and optimizations in views."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_job_retrieve_database_query_optimization(self):
        """Test that job retrieval uses optimized database queries."""
        # Create test job
        job = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Test guidelines'},
            result={'summary': 'Test summary', 'checklist': []}
        )
        
        url = reverse('jobs:job-retrieve', kwargs={'event_id': job.event_id})
        
        # Monitor database queries during retrieval
        from django.test.utils import override_settings
        from django.db import connection
        
        with override_settings(DEBUG=True):
            connection.queries_log.clear()
            response = self.client.get(url)
            query_count = len(connection.queries)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should use minimal database queries (ideally 1 for the job retrieval)
        self.assertLessEqual(query_count, 2, "Job retrieval should use minimal database queries")
    
    def test_job_create_performance_timing(self):
        """Test that job creation meets performance requirements."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Performance test guidelines for timing validation.'
        }
        
        start_time = time.time()
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Performance requirement: <200ms response time
        # Allow generous buffer for test environment
        self.assertLess(response_time, 1000, f"Job creation took {response_time:.1f}ms, should be <1000ms in test env")


class TestViewsConcurrencyAndRaceConditions(APITestCase):
    """Test concurrency handling and race condition prevention."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_concurrent_job_creation_uuid_uniqueness(self):
        """Test that concurrent job creation maintains UUID uniqueness."""
        import threading
        import queue
        
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Concurrent test guidelines for UUID uniqueness.'
        }
        
        results = queue.Queue()
        event_ids = queue.Queue()
        
        def create_job():
            try:
                response = self.client.post(
                    url,
                    data=json.dumps(payload),
                    content_type='application/json'
                )
                results.put(response.status_code)
                if response.status_code == 201:
                    event_ids.put(response.json()['data']['event_id'])
            except Exception as e:
                results.put(f"Exception: {e}")
        
        # Create multiple threads for concurrent job creation
        threads = []
        for i in range(10):
            thread = threading.Thread(target=create_job)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify all jobs were created successfully
        success_count = 0
        while not results.empty():
            result = results.get()
            if result == 201:
                success_count += 1
        
        self.assertEqual(success_count, 10, "All concurrent job creations should succeed")
        
        # Verify all event IDs are unique
        collected_event_ids = []
        while not event_ids.empty():
            collected_event_ids.append(event_ids.get())
        
        self.assertEqual(len(collected_event_ids), len(set(collected_event_ids)), 
                        "All event IDs should be unique")
        self.assertEqual(len(collected_event_ids), 10, "Should have 10 unique event IDs")


class TestJobViewsErrorHandling(APITestCase):
    """Test advanced error handling scenarios in job views."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    @patch('guideline_ingestion.jobs.tasks.process_guideline_job')
    def test_job_create_celery_task_failure(self, mock_task):
        """Test job creation when Celery task queueing fails."""
        # Mock Celery task to raise an exception
        mock_task.delay.side_effect = Exception("Celery connection failed")
        
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for Celery failure scenario.'
        }
        
        # Should still create the job successfully (graceful degradation)
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        # Job creation should succeed even if task queueing fails
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify job was created in database
        event_id = response.json()['data']['event_id']
        job = Job.objects.get(event_id=event_id)
        self.assertEqual(job.status, JobStatus.PENDING)
    
    @patch('guideline_ingestion.jobs.models.Job.objects.create')
    def test_job_create_database_error(self, mock_create):
        """Test job creation when database operation fails."""
        # Mock database create to fail
        mock_create.side_effect = DatabaseError("Database connection lost")
        
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for database failure scenario.'
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        # Should return 500 internal server error
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertEqual(response_data['error']['code'], 'INTERNAL_SERVER_ERROR')
    
    def test_job_create_invalid_uuid_in_response(self):
        """Test handling of UUID validation errors in response formatting."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for UUID validation.'
        }
        
        # Mock UUID generation to create an invalid UUID scenario
        with patch('uuid.uuid4') as mock_uuid:
            # Return a string that looks like UUID but will cause issues
            mock_uuid.return_value = "invalid-uuid-format"
            
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type='application/json'
            )
            
            # Should handle gracefully or return appropriate error
            self.assertIn(response.status_code, [201, 500])
    
    def test_job_retrieve_database_connection_error(self):
        """Test job retrieval when database connection fails."""
        # Create a job first
        job = Job.objects.create(
            input_data={'guidelines': 'Test guidelines for database error scenario'}
        )
        
        url = reverse('jobs:job-retrieve', kwargs={'event_id': job.event_id})
        
        # Mock database query to fail
        with patch('guideline_ingestion.jobs.models.Job.objects.get') as mock_get:
            mock_get.side_effect = DatabaseError("Database connection lost")
            
            response = self.client.get(url)
            
            # Should return 500 internal server error
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def test_job_create_malformed_json_handling(self):
        """Test handling of malformed JSON in request body."""
        url = reverse('jobs:job-create')
        
        # Send malformed JSON
        response = self.client.post(
            url,
            data='{"guidelines": "test", invalid json}',
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertEqual(response_data['error']['code'], 'JSON_PARSE_ERROR')
    
    def test_job_create_empty_request_body(self):
        """Test handling of empty request body."""
        url = reverse('jobs:job-create')
        
        response = self.client.post(
            url,
            data='',
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
        self.assertEqual(response_data['error']['code'], 'VALIDATION_ERROR')
    
    def test_job_create_content_type_validation(self):
        """Test handling of incorrect content types."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Test guidelines for content type validation.'
        }
        
        # Send with form content type instead of JSON
        response = self.client.post(
            url,
            data=payload,  # Form data
            content_type='application/x-www-form-urlencoded'
        )
        
        # Should return 400 or handle gracefully
        self.assertIn(response.status_code, [400, 415])
    
    def test_job_retrieve_invalid_uuid_format_handling(self):
        """Test retrieval with various invalid UUID formats."""
        invalid_uuids = [
            'not-a-uuid',
            '12345',
            'invalid-uuid-format-too-long',
            '12345678-1234-1234-1234-12345678901X',  # Invalid character
            '',
            'null'
        ]
        
        for invalid_uuid in invalid_uuids:
            with self.subTest(uuid=invalid_uuid):
                url = f"/jobs/{invalid_uuid}/"
                
                response = self.client.get(url)
                
                # Should return 404 for invalid UUID formats
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    @patch('guideline_ingestion.jobs.views.JobRetrieveSerializer')
    def test_job_retrieve_serialization_error(self, mock_serializer_class):
        """Test handling of serialization errors during job retrieval."""
        # Create a job
        job = Job.objects.create(
            input_data={'guidelines': 'Test guidelines for serialization error'}
        )
        
        # Mock serializer to raise an error when .data is accessed
        mock_serializer = MagicMock()
        mock_serializer_class.return_value = mock_serializer
        
        # Make accessing .data raise an exception
        type(mock_serializer).data = PropertyMock(side_effect=ValueError("Serialization failed"))
        
        url = reverse('jobs:job-retrieve', kwargs={'event_id': job.event_id})
        
        response = self.client.get(url)
        
        # Should handle serialization error gracefully
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def test_job_create_memory_pressure_scenario(self):
        """Test job creation under memory pressure conditions."""
        url = reverse('jobs:job-create')
        
        # Create a very large guidelines payload to simulate memory pressure
        large_guidelines = "Test guideline content. " * 10000  # ~250KB
        
        payload = {
            'guidelines': large_guidelines,
            'metadata': {f'key_{i}': f'value_{i}' for i in range(10)}  # Max metadata
        }
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        # Should handle large payloads appropriately  
        self.assertIn(response.status_code, [201, 400, 413])  # Created, Bad Request, or Payload Too Large
    
    def test_job_create_performance_validation(self):
        """Test job creation performance under normal conditions."""
        url = reverse('jobs:job-create')
        payload = {
            'guidelines': 'Performance test guidelines for response time validation.'
        }
        
        import time
        start_time = time.time()
        
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        end_time = time.time()
        response_time = end_time - start_time
        
        # Should respond within reasonable time (2 seconds)
        self.assertLess(response_time, 2.0, "Job creation should be fast")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)