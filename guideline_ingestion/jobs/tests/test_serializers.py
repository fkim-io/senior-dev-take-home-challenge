"""
Tests for jobs API serializers (TDD Red Phase).

This module contains comprehensive tests for request/response serializers,
validation logic, and data transformation.
"""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from django.test import TestCase
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from guideline_ingestion.jobs.models import Job, JobStatus
from guideline_ingestion.jobs.serializers import (
    JobCreateSerializer,
    JobRetrieveSerializer,
    JobListSerializer
)


class TestJobCreateSerializer(TestCase):
    """Test JobCreateSerializer validation and data transformation."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_data = {
            'guidelines': 'This is a comprehensive test guideline document that contains sufficient content for processing.',
            'callback_url': 'https://example.com/callback',
            'priority': 'normal',
            'metadata': {
                'source': 'test',
                'version': '1.0',
                'department': 'engineering'
            }
        }
        
        self.minimal_data = {
            'guidelines': 'Minimal valid guidelines for testing purposes.'
        }
    
    def test_serializer_valid_full_data(self):
        """Test serializer with valid full data."""
        serializer = JobCreateSerializer(data=self.valid_data)
        
        self.assertTrue(serializer.is_valid())
        
        validated_data = serializer.validated_data
        self.assertEqual(validated_data['guidelines'], self.valid_data['guidelines'])
        self.assertEqual(validated_data['callback_url'], self.valid_data['callback_url'])
        self.assertEqual(validated_data['priority'], self.valid_data['priority'])
        self.assertEqual(validated_data['metadata'], self.valid_data['metadata'])
    
    def test_serializer_valid_minimal_data(self):
        """Test serializer with minimal required data."""
        serializer = JobCreateSerializer(data=self.minimal_data)
        
        self.assertTrue(serializer.is_valid())
        
        validated_data = serializer.validated_data
        self.assertEqual(validated_data['guidelines'], self.minimal_data['guidelines'])
        self.assertNotIn('callback_url', validated_data)
        self.assertEqual(validated_data.get('priority', 'normal'), 'normal')
        self.assertEqual(validated_data.get('metadata', {}), {})
    
    def test_guidelines_field_required(self):
        """Test that guidelines field is required."""
        data = {'priority': 'high'}
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('guidelines', serializer.errors)
        self.assertIn('required', str(serializer.errors['guidelines'][0]).lower())
    
    def test_guidelines_field_min_length_validation(self):
        """Test guidelines field minimum length validation."""
        data = {'guidelines': 'Short'}  # 5 characters, less than 10
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('guidelines', serializer.errors)
        self.assertIn('10', str(serializer.errors['guidelines'][0]))
    
    def test_guidelines_field_max_length_validation(self):
        """Test guidelines field maximum length validation."""
        data = {'guidelines': 'A' * 10001}  # More than 10000 characters
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('guidelines', serializer.errors)
        self.assertIn('10000', str(serializer.errors['guidelines'][0]))
    
    def test_guidelines_field_whitespace_validation(self):
        """Test guidelines field rejects only whitespace."""
        data = {'guidelines': '   \n\t   '}  # Only whitespace
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('guidelines', serializer.errors)
    
    def test_callback_url_validation_valid_https(self):
        """Test callback URL accepts valid HTTPS URLs."""
        data = {
            'guidelines': 'Valid guidelines for callback URL testing.',
            'callback_url': 'https://api.example.com/webhooks/jobs'
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertTrue(serializer.is_valid())
    
    def test_callback_url_validation_rejects_http(self):
        """Test callback URL rejects HTTP URLs (requires HTTPS)."""
        data = {
            'guidelines': 'Valid guidelines for callback URL testing.',
            'callback_url': 'http://api.example.com/webhooks/jobs'
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('callback_url', serializer.errors)
        self.assertIn('https', str(serializer.errors['callback_url'][0]).lower())
    
    def test_callback_url_validation_rejects_invalid_url(self):
        """Test callback URL rejects invalid URL formats."""
        data = {
            'guidelines': 'Valid guidelines for callback URL testing.',
            'callback_url': 'not-a-valid-url'
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('callback_url', serializer.errors)
    
    def test_priority_field_valid_choices(self):
        """Test priority field accepts valid choices."""
        valid_priorities = ['low', 'normal', 'high']
        
        for priority in valid_priorities:
            data = {
                'guidelines': 'Valid guidelines for priority testing.',
                'priority': priority
            }
            serializer = JobCreateSerializer(data=data)
            
            self.assertTrue(serializer.is_valid(), f"Priority '{priority}' should be valid")
            self.assertEqual(serializer.validated_data['priority'], priority)
    
    def test_priority_field_invalid_choice(self):
        """Test priority field rejects invalid choices."""
        data = {
            'guidelines': 'Valid guidelines for priority testing.',
            'priority': 'invalid'
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('priority', serializer.errors)
    
    def test_priority_field_default_value(self):
        """Test priority field defaults to 'normal' when not provided."""
        data = {'guidelines': 'Valid guidelines for default priority testing.'}
        serializer = JobCreateSerializer(data=data)
        
        self.assertTrue(serializer.is_valid())
        # Default value is set by the serializer
        self.assertEqual(serializer.validated_data['priority'], 'normal')
    
    def test_metadata_field_valid_structure(self):
        """Test metadata field accepts valid key-value structure."""
        data = {
            'guidelines': 'Valid guidelines for metadata testing.',
            'metadata': {
                'source': 'api',
                'user_id': '12345',
                'department': 'engineering',
                'version': '2.1'
            }
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['metadata'], data['metadata'])
    
    def test_metadata_field_size_limit(self):
        """Test metadata field enforces size limit."""
        # Create metadata > 1KB with fewer than 10 keys
        large_metadata = {f'key_{i}': 'x' * 150 for i in range(8)}  # 8 keys * ~150 chars = ~1200 bytes
        data = {
            'guidelines': 'Valid guidelines for metadata size testing.',
            'metadata': large_metadata
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
        self.assertIn('1024', str(serializer.errors['metadata'][0]))
    
    def test_metadata_field_key_count_limit(self):
        """Test metadata field enforces maximum key count."""
        # Create metadata with > 10 keys
        too_many_keys = {f'key_{i}': f'value_{i}' for i in range(15)}
        data = {
            'guidelines': 'Valid guidelines for metadata key count testing.',
            'metadata': too_many_keys
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
        self.assertIn('10', str(serializer.errors['metadata'][0]))
    
    def test_metadata_field_empty_dict_valid(self):
        """Test metadata field accepts empty dictionary."""
        data = {
            'guidelines': 'Valid guidelines for empty metadata testing.',
            'metadata': {}
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['metadata'], {})
    
    def test_serializer_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        data = {
            'guidelines': 'Valid guidelines for extra fields testing.',
            'unknown_field': 'should be ignored',
            'another_extra': 12345
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertTrue(serializer.is_valid())
        self.assertNotIn('unknown_field', serializer.validated_data)
        self.assertNotIn('another_extra', serializer.validated_data)


class TestJobRetrieveSerializer(TestCase):
    """Test JobRetrieveSerializer for different job states."""
    
    def setUp(self):
        """Set up test jobs in different states."""
        # PENDING job
        self.pending_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={
                'guidelines': 'Test guidelines for pending job',
                'priority': 'normal'
            }
        )
        
        # PROCESSING job
        self.processing_job = Job.objects.create(
            status=JobStatus.PROCESSING,
            input_data={
                'guidelines': 'Test guidelines for processing job',
                'priority': 'high'
            },
            started_at=timezone.now()
        )
        
        # COMPLETED job
        self.completed_job = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={
                'guidelines': 'Test guidelines for completed job',
                'priority': 'normal'
            },
            started_at=timezone.now() - timedelta(minutes=2),
            completed_at=timezone.now(),
            result={
                'summary': 'Test summary of the guidelines',
                'checklist': [
                    {
                        'id': 1,
                        'title': 'Implement security measures',
                        'description': 'Ensure proper authentication',
                        'priority': 'high',
                        'category': 'security'
                    },
                    {
                        'id': 2,
                        'title': 'Configure monitoring',
                        'description': 'Set up application monitoring',
                        'priority': 'medium',
                        'category': 'operations'
                    }
                ]
            }
        )
        
        # FAILED job
        self.failed_job = Job.objects.create(
            status=JobStatus.FAILED,
            input_data={
                'guidelines': 'Test guidelines for failed job',
                'priority': 'normal'
            },
            started_at=timezone.now() - timedelta(minutes=1),
            completed_at=timezone.now(),
            error_message='OpenAI API rate limit exceeded',
            retry_count=3
        )
    
    def test_serialize_pending_job(self):
        """Test serialization of PENDING job."""
        serializer = JobRetrieveSerializer(self.pending_job)
        data = serializer.data
        
        # Common fields
        self.assertEqual(data['event_id'], str(self.pending_job.event_id))
        self.assertEqual(data['status'], 'PENDING')
        self.assertIn('created_at', data)
        
        # PENDING-specific fields
        self.assertIn('estimated_completion', data)
        self.assertIn('queue_position', data)
        
        # Fields that should not be present
        self.assertNotIn('started_at', data)
        self.assertNotIn('result', data)
        self.assertNotIn('error_message', data)
    
    def test_serialize_processing_job(self):
        """Test serialization of PROCESSING job."""
        serializer = JobRetrieveSerializer(self.processing_job)
        data = serializer.data
        
        # Common fields
        self.assertEqual(data['event_id'], str(self.processing_job.event_id))
        self.assertEqual(data['status'], 'PROCESSING')
        self.assertIn('created_at', data)
        
        # PROCESSING-specific fields
        self.assertIn('started_at', data)
        self.assertIn('estimated_completion', data)
        self.assertIn('current_step', data)
        
        # Fields that should not be present
        self.assertNotIn('result', data)
        self.assertNotIn('error_message', data)
    
    def test_serialize_completed_job(self):
        """Test serialization of COMPLETED job."""
        serializer = JobRetrieveSerializer(self.completed_job)
        data = serializer.data
        
        # Common fields
        self.assertEqual(data['event_id'], str(self.completed_job.event_id))
        self.assertEqual(data['status'], 'COMPLETED')
        self.assertIn('created_at', data)
        
        # COMPLETED-specific fields
        self.assertIn('completed_at', data)
        self.assertIn('processing_time_seconds', data)
        self.assertIn('result', data)
        
        # Verify result structure
        result = data['result']
        self.assertIn('summary', result)
        self.assertIn('checklist', result)
        self.assertIsInstance(result['checklist'], list)
        
        # Verify checklist items
        checklist = result['checklist']
        self.assertEqual(len(checklist), 2)
        
        for item in checklist:
            self.assertIn('id', item)
            self.assertIn('title', item)
            self.assertIn('description', item)
            self.assertIn('priority', item)
            self.assertIn('category', item)
        
        # Verify metadata
        self.assertIn('metadata', data)
        metadata = data['metadata']
        self.assertIn('gpt_model_used', metadata)
        self.assertIn('tokens_consumed', metadata)
        self.assertIn('processing_steps', metadata)
    
    def test_serialize_failed_job(self):
        """Test serialization of FAILED job."""
        serializer = JobRetrieveSerializer(self.failed_job)
        data = serializer.data
        
        # Common fields
        self.assertEqual(data['event_id'], str(self.failed_job.event_id))
        self.assertEqual(data['status'], 'FAILED')
        self.assertIn('created_at', data)
        
        # FAILED-specific fields
        self.assertIn('error_message', data)
        self.assertIn('completed_at', data)
        self.assertIn('retry_count', data)
        self.assertEqual(data['error_message'], 'OpenAI API rate limit exceeded')
        self.assertEqual(data['retry_count'], 3)
        
        # Fields that should not be present
        self.assertNotIn('result', data)
    
    def test_processing_time_calculation(self):
        """Test processing time calculation for completed jobs."""
        serializer = JobRetrieveSerializer(self.completed_job)
        data = serializer.data
        
        self.assertIn('processing_time_seconds', data)
        
        # Calculate expected processing time
        expected_time = (self.completed_job.completed_at - self.completed_job.started_at).total_seconds()
        self.assertAlmostEqual(data['processing_time_seconds'], expected_time, places=1)
    
    def test_estimated_completion_calculation(self):
        """Test estimated completion time calculation."""
        serializer = JobRetrieveSerializer(self.pending_job)
        data = serializer.data
        
        self.assertIn('estimated_completion', data)
        
        # Verify it's a future timestamp
        estimated = datetime.fromisoformat(data['estimated_completion'].replace('Z', '+00:00'))
        self.assertGreater(estimated, timezone.now())
    
    def test_queue_position_calculation(self):
        """Test queue position calculation for pending jobs."""
        # Create additional pending jobs to test queue position
        earlier_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Earlier job'},
            created_at=timezone.now() - timedelta(minutes=1)
        )
        
        serializer = JobRetrieveSerializer(self.pending_job)
        data = serializer.data
        
        self.assertIn('queue_position', data)
        self.assertIsInstance(data['queue_position'], int)
        self.assertGreaterEqual(data['queue_position'], 1)


class TestJobListSerializer(TestCase):
    """Test JobListSerializer for job listing endpoints."""
    
    def setUp(self):
        """Set up multiple test jobs."""
        self.jobs = []
        base_time = timezone.now()
        
        # Create PENDING job
        job_pending = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Test guidelines 0'},
            created_at=base_time
        )
        self.jobs.append(job_pending)
        
        # Create PROCESSING job (needs started_at)
        job_processing = Job.objects.create(
            status=JobStatus.PROCESSING,
            input_data={'guidelines': 'Test guidelines 1'},
            created_at=base_time - timedelta(minutes=1),
            started_at=base_time - timedelta(minutes=1)
        )
        self.jobs.append(job_processing)
        
        # Create COMPLETED job (needs started_at and completed_at)
        job_completed = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Test guidelines 2'},
            result={'summary': 'Test summary', 'checklist': []},
            created_at=base_time - timedelta(minutes=2),
            started_at=base_time - timedelta(minutes=2),
            completed_at=base_time - timedelta(minutes=1)
        )
        self.jobs.append(job_completed)
    
    def test_serialize_job_list(self):
        """Test serialization of multiple jobs."""
        serializer = JobListSerializer(self.jobs, many=True)
        data = serializer.data
        
        self.assertEqual(len(data), 3)
        
        for i, job_data in enumerate(data):
            self.assertIn('event_id', job_data)
            self.assertIn('status', job_data)
            self.assertIn('created_at', job_data)
            self.assertIn('updated_at', job_data)
            
            # List view should not include detailed result data
            self.assertNotIn('result', job_data)
            self.assertNotIn('error_message', job_data)
    
    def test_serialize_empty_list(self):
        """Test serialization of empty job list."""
        serializer = JobListSerializer([], many=True)
        data = serializer.data
        
        self.assertEqual(data, [])


class TestSerializerErrorFormatting(TestCase):
    """Test error formatting and messages."""
    
    def test_validation_error_format(self):
        """Test that validation errors are properly formatted."""
        data = {
            'guidelines': 'Short',  # Too short
            'callback_url': 'invalid-url',  # Invalid URL
            'priority': 'invalid'  # Invalid choice
        }
        
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        
        errors = serializer.errors
        self.assertIn('guidelines', errors)
        self.assertIn('callback_url', errors)
        self.assertIn('priority', errors)
        
        # Verify error messages are user-friendly
        for field, error_list in errors.items():
            for error in error_list:
                self.assertIsInstance(error, str)
                self.assertGreater(len(error), 5)  # Non-trivial error message
    
    def test_nested_validation_errors(self):
        """Test validation errors for nested fields like metadata."""
        data = {
            'guidelines': 'Valid guidelines for nested validation testing.',
            'metadata': {f'key_{i}': 'x' * 100 for i in range(15)}  # Too many keys
        }
        
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
    
    def test_field_required_error_message(self):
        """Test specific error message for required fields."""
        serializer = JobCreateSerializer(data={})
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('guidelines', serializer.errors)
        
        error_message = str(serializer.errors['guidelines'][0])
        self.assertIn('required', error_message.lower())


class TestSerializerEdgeCasesAndValidation(TestCase):
    """Test edge cases and additional validation scenarios."""
    
    def test_job_create_serializer_callback_url_edge_cases(self):
        """Test callback URL validation edge cases."""
        # Test empty string (should be valid - treated as None)
        data = {
            'guidelines': 'Valid guidelines for callback URL edge case testing.',
            'callback_url': ''
        }
        serializer = JobCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test None value (should be valid)
        data['callback_url'] = None
        serializer = JobCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test whitespace-only URL (gets normalized to empty string - should be valid)
        data['callback_url'] = '   '
        serializer = JobCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        # Verify whitespace was normalized to empty string
        self.assertEqual(serializer.validated_data['callback_url'], '')
    
    def test_job_create_serializer_metadata_non_serializable_values(self):
        """Test metadata validation with non-serializable values."""
        data = {
            'guidelines': 'Valid guidelines for metadata testing.',
            'metadata': {
                'datetime_obj': datetime.now(),  # Non-serializable
                'function': lambda x: x,  # Non-serializable
            }
        }
        serializer = JobCreateSerializer(data=data)
        
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
        self.assertIn('valid json', str(serializer.errors['metadata'][0]).lower())
    
    def test_job_create_serializer_metadata_exactly_at_limits(self):
        """Test metadata validation at exact limits."""
        # Test exactly 10 keys (should be valid)
        metadata_10_keys = {f'key_{i}': f'value_{i}' for i in range(10)}
        data = {
            'guidelines': 'Valid guidelines for metadata limit testing.',
            'metadata': metadata_10_keys
        }
        serializer = JobCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test 11 keys (should be invalid)
        metadata_11_keys = {f'key_{i}': f'value_{i}' for i in range(11)}
        data['metadata'] = metadata_11_keys
        serializer = JobCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
    
    def test_job_create_serializer_metadata_size_boundary(self):
        """Test metadata size validation at boundary conditions."""
        # Create metadata that's exactly 1024 bytes
        # Each character is 1 byte, so we need exactly 1024 characters total
        # JSON format: {"key": "value"} = 15 characters base + content
        # We'll create a single key-value pair that totals exactly 1024 bytes
        
        base_json = '{"k":"'  # 6 characters
        end_json = '"}'       # 2 characters  
        # Total overhead: 8 characters
        # Available for key and value: 1024 - 8 = 1016 characters
        # Key "k" = 1 character, so value can be 1015 characters
        
        large_value = 'x' * 1015  # Exactly at limit
        metadata_at_limit = {'k': large_value}
        
        data = {
            'guidelines': 'Valid guidelines for metadata size boundary testing.',
            'metadata': metadata_at_limit
        }
        serializer = JobCreateSerializer(data=data)
        
        # Should be valid (at limit)
        self.assertTrue(serializer.is_valid())
        
        # Test slightly over limit  
        oversized_value = 'x' * 1017  # 2 characters over to exceed 1024
        metadata_over_limit = {'k': oversized_value}
        data['metadata'] = metadata_over_limit
        serializer = JobCreateSerializer(data=data)
        
        # Should be invalid (over limit)
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
    
    def test_job_create_serializer_guidelines_whitespace_normalization(self):
        """Test guidelines field whitespace handling."""
        # Test leading/trailing whitespace is stripped
        data = {'guidelines': '   Valid guidelines with whitespace   '}
        serializer = JobCreateSerializer(data=data)
        
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['guidelines'], 'Valid guidelines with whitespace')
        
        # Test internal whitespace is preserved
        data = {'guidelines': 'Guidelines with\n\tinternal   whitespace'}
        serializer = JobCreateSerializer(data=data)
        
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['guidelines'], 'Guidelines with\n\tinternal   whitespace')
    
    def test_job_retrieve_serializer_edge_case_timestamps(self):
        """Test JobRetrieveSerializer with edge case timestamp scenarios."""
        from datetime import timedelta
        
        # Test job with null timestamps
        job_minimal = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Minimal job'}
        )
        
        serializer = JobRetrieveSerializer(job_minimal)
        data = serializer.data
        
        # Should handle null timestamps gracefully
        self.assertIsNone(data.get('started_at'))
        self.assertIsNone(data.get('completed_at'))
        self.assertIsNone(data.get('processing_time_seconds'))
        
        # Test job with very short processing time
        now = timezone.now()
        job_fast = Job.objects.create(
            status=JobStatus.COMPLETED,
            input_data={'guidelines': 'Fast job'},
            started_at=now,
            completed_at=now + timedelta(milliseconds=500),  # 0.5 seconds
            result={'summary': 'Fast summary', 'checklist': []}
        )
        
        serializer = JobRetrieveSerializer(job_fast)
        data = serializer.data
        
        # Should calculate processing time correctly for sub-second jobs
        self.assertIsNotNone(data.get('processing_time_seconds'))
        self.assertGreater(data['processing_time_seconds'], 0)
        self.assertLess(data['processing_time_seconds'], 1)
    
    def test_job_retrieve_serializer_queue_position_edge_cases(self):
        """Test queue position calculation edge cases."""
        now = timezone.now()
        
        # Count existing pending jobs before our test
        existing_pending_count = Job.objects.filter(status=JobStatus.PENDING).count()
        
        # Create single pending job
        single_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Single job'},
            created_at=now
        )
        
        serializer = JobRetrieveSerializer(single_job)
        data = serializer.data
        
        # Should be last in queue (after existing pending jobs)
        expected_position = existing_pending_count + 1
        self.assertEqual(data.get('queue_position'), expected_position)
        
        # Create job with same timestamp (edge case for ordering)
        same_time_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Same time job'},
            created_at=now  # Exact same timestamp
        )
        
        serializer = JobRetrieveSerializer(same_time_job)
        data = serializer.data
        
        # Should handle same timestamp correctly (position depends on ID ordering)
        self.assertIsInstance(data.get('queue_position'), int)
        self.assertGreaterEqual(data['queue_position'], 1)
    
    def test_job_retrieve_serializer_status_specific_field_filtering(self):
        """Test that status-specific fields are properly filtered."""
        # Test PENDING job has only relevant fields
        pending_job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': 'Pending job'}
        )
        
        serializer = JobRetrieveSerializer(pending_job)
        data = serializer.data
        
        # Should include PENDING-specific fields
        pending_fields = ['event_id', 'status', 'created_at', 'updated_at', 'estimated_completion', 'queue_position']
        for field in pending_fields:
            self.assertIn(field, data)
        
        # Should exclude non-PENDING fields  
        excluded_fields = ['started_at', 'completed_at', 'result', 'error_message', 'current_step', 'metadata']
        for field in excluded_fields:
            self.assertNotIn(field, data)
    
    def test_job_list_serializer_minimal_fields(self):
        """Test JobListSerializer includes only minimal necessary fields."""
        jobs = []
        now = timezone.now()
        
        for i, status in enumerate([JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.COMPLETED, JobStatus.FAILED]):
            # Set appropriate timestamps based on status to respect database constraints
            job_data = {
                'status': status,
                'input_data': {'guidelines': f'Job {i}'}
            }
            
            if status in [JobStatus.PROCESSING, JobStatus.COMPLETED, JobStatus.FAILED]:
                job_data['started_at'] = now
            
            if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                job_data['completed_at'] = now + timedelta(seconds=10)
            
            job = Job.objects.create(**job_data)
            jobs.append(job)
        
        serializer = JobListSerializer(jobs, many=True)
        data = serializer.data
        
        # Verify minimal field set for all jobs
        expected_fields = ['event_id', 'status', 'created_at', 'updated_at']
        excluded_fields = ['result', 'error_message', 'input_data', 'metadata', 'processing_time_seconds']
        
        for job_data in data:
            # Should include minimal fields
            for field in expected_fields:
                self.assertIn(field, job_data)
            
            # Should exclude detailed fields
            for field in excluded_fields:
                self.assertNotIn(field, job_data)
    
    def test_serializer_unicode_and_special_characters(self):
        """Test serializers handle Unicode and special characters properly."""
        # Test guidelines with Unicode characters
        unicode_data = {
            'guidelines': 'Guidelines with émojis 🚀 and ünïcödé characters: 测试文档',
            'metadata': {
                'description': 'Test with spéciäl characters',
                'emoji': '🎯📝',
                'chinese': '中文测试'
            }
        }
        
        serializer = JobCreateSerializer(data=unicode_data)
        self.assertTrue(serializer.is_valid())
        
        # Verify Unicode is preserved
        validated_data = serializer.validated_data
        self.assertIn('émojis 🚀', validated_data['guidelines'])
        self.assertIn('ünïcödé', validated_data['guidelines'])
        self.assertEqual(validated_data['metadata']['emoji'], '🎯📝')
        self.assertEqual(validated_data['metadata']['chinese'], '中文测试')
    
    def test_serializer_extreme_values(self):
        """Test serializers with extreme but valid values."""
        # Test maximum length guidelines
        max_guidelines = 'A' * 10000  # Exactly at max length
        data = {
            'guidelines': max_guidelines,
            'priority': 'low',  # Test all priority values
        }
        
        serializer = JobCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(len(serializer.validated_data['guidelines']), 10000)
        
        # Test minimum length guidelines
        min_guidelines = 'A' * 10  # Exactly at min length
        data['guidelines'] = min_guidelines
        
        serializer = JobCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(len(serializer.validated_data['guidelines']), 10)


class TestSerializerValidationEdgeCases(TestCase):
    """Test edge cases for serializer validation."""
    
    def test_callback_url_edge_cases(self):
        """Test callback URL validation with edge cases."""
        edge_case_urls = [
            # Valid HTTPS URLs
            ('https://example.com', True),
            ('https://example.com/', True),
            ('https://example.com/callback', True),
            ('https://subdomain.example.com/path', True),
            ('https://example.com:8443/callback', True),
            
            # Invalid URLs (non-HTTPS)
            ('http://example.com', False),
            ('ftp://example.com', False),
            ('ws://example.com', False),
            
            # Edge cases  
            ('https://', False),  # Incomplete URL
            ('https://localhost', True),  # Localhost is valid
            ('https://127.0.0.1', True),  # IP address is valid  
            ('https://example.com/path?query=1&other=2', True),  # Query parameters
        ]
        
        for url, should_be_valid in edge_case_urls:
            with self.subTest(url=url):
                data = {
                    'guidelines': 'Test guidelines for callback URL validation.',
                    'callback_url': url
                }
                serializer = JobCreateSerializer(data=data)
                
                if should_be_valid:
                    self.assertTrue(serializer.is_valid(), f"URL {url} should be valid")
                else:
                    self.assertFalse(serializer.is_valid(), f"URL {url} should be invalid")
                    self.assertIn('callback_url', serializer.errors)
    
    def test_metadata_non_serializable_values(self):
        """Test metadata validation with non-serializable values."""
        import datetime
        from decimal import Decimal
        
        non_serializable_metadata = {
            'datetime': datetime.datetime.now(),  # Not JSON serializable
            'decimal': Decimal('10.5'),  # Not JSON serializable
            'set': {1, 2, 3},  # Not JSON serializable
            'function': lambda x: x,  # Not JSON serializable
        }
        
        data = {
            'guidelines': 'Test guidelines for non-serializable metadata.',
            'metadata': non_serializable_metadata
        }
        
        serializer = JobCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
        self.assertIn('valid json', str(serializer.errors['metadata']).lower())
    
    def test_metadata_nested_objects_size_calculation(self):
        """Test metadata size calculation with nested objects."""
        # Create deeply nested metadata that exceeds size limit
        nested_metadata = {
            'level1': {
                'level2': {
                    'level3': {
                        'data': 'x' * 800  # Large string in nested structure
                    }
                }
            },
            'additional': 'y' * 300  # Additional data to push over 1KB limit
        }
        
        data = {
            'guidelines': 'Test guidelines for nested metadata size validation.',
            'metadata': nested_metadata
        }
        
        serializer = JobCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
        self.assertIn('size', str(serializer.errors['metadata']).lower())
    
    def test_metadata_unicode_size_calculation(self):
        """Test metadata size calculation with Unicode characters."""
        # Unicode characters may take multiple bytes
        unicode_metadata = {
            'emoji_string': '🚀' * 200,  # Emojis are 4 bytes each in UTF-8
            'chinese_text': '测试' * 100,  # Chinese characters are 3 bytes each
        }
        
        data = {
            'guidelines': 'Test guidelines for Unicode metadata size.',
            'metadata': unicode_metadata
        }
        
        serializer = JobCreateSerializer(data=data)
        # Should be invalid due to large Unicode character byte size
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)
    
    def test_guidelines_unicode_normalization(self):
        """Test guidelines field handles Unicode normalization."""
        # Test different Unicode normalization forms (ensuring minimum length)
        guidelines_variants = [
            'café guidelines for testing unicode normalization',  # Composed form (é as single character)
            'cafe\u0301 guidelines for testing unicode normalization',  # Decomposed form (e + combining acute accent)
        ]
        
        for guidelines in guidelines_variants:
            with self.subTest(guidelines=guidelines):
                data = {'guidelines': guidelines}
                serializer = JobCreateSerializer(data=data)
                self.assertTrue(serializer.is_valid())
                
                # Should preserve Unicode content
                validated = serializer.validated_data['guidelines']
                self.assertIn('caf', validated)  # Should contain the base content
                self.assertTrue(len(validated) > 10)  # Should meet minimum length
    
    def test_priority_field_case_sensitivity(self):
        """Test priority field case sensitivity."""
        case_variants = [
            ('low', True),
            ('LOW', False),  # Should be case sensitive
            ('Low', False),
            ('normal', True),  # 'normal' is a valid choice, not 'medium'
            ('NORMAL', False),
            ('high', True),
            ('HIGH', False),
        ]
        
        for priority, should_be_valid in case_variants:
            with self.subTest(priority=priority):
                data = {
                    'guidelines': 'Test guidelines for priority case sensitivity.',
                    'priority': priority
                }
                serializer = JobCreateSerializer(data=data)
                
                if should_be_valid:
                    self.assertTrue(serializer.is_valid())
                else:
                    self.assertFalse(serializer.is_valid())
                    self.assertIn('priority', serializer.errors)
    
    def test_metadata_empty_string_keys_and_values(self):
        """Test metadata validation with empty strings."""
        empty_string_metadata = {
            '': 'value_for_empty_key',  # Empty key
            'key_for_empty_value': '',  # Empty value
            'normal_key': 'normal_value'
        }
        
        data = {
            'guidelines': 'Test guidelines for empty string metadata.',
            'metadata': empty_string_metadata
        }
        
        serializer = JobCreateSerializer(data=data)
        # Should be valid - empty strings are allowed in metadata
        self.assertTrue(serializer.is_valid())
        
        validated = serializer.validated_data['metadata']
        self.assertIn('', validated)  # Empty key should be preserved
        self.assertEqual(validated['key_for_empty_value'], '')
    
    def test_metadata_null_and_boolean_values(self):
        """Test metadata validation with null and boolean values."""
        mixed_type_metadata = {
            'null_value': None,
            'true_value': True,
            'false_value': False,
            'zero_value': 0,
            'empty_list': [],
            'empty_dict': {}
        }
        
        data = {
            'guidelines': 'Test guidelines for mixed type metadata.',
            'metadata': mixed_type_metadata
        }
        
        serializer = JobCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        validated = serializer.validated_data['metadata']
        self.assertIsNone(validated['null_value'])
        self.assertTrue(validated['true_value'])
        self.assertFalse(validated['false_value'])
        self.assertEqual(validated['zero_value'], 0)
        self.assertEqual(validated['empty_list'], [])
        self.assertEqual(validated['empty_dict'], {})
    
    def test_guidelines_only_whitespace_variations(self):
        """Test guidelines validation with various whitespace patterns."""
        whitespace_variations = [
            '   ',  # Only spaces
            '\t\t',  # Only tabs
            '\n\n',  # Only newlines
            ' \t\n ',  # Mixed whitespace
            '',  # Empty string
        ]
        
        for guidelines in whitespace_variations:
            with self.subTest(guidelines=repr(guidelines)):
                data = {'guidelines': guidelines}
                serializer = JobCreateSerializer(data=data)
                
                self.assertFalse(serializer.is_valid())
                self.assertIn('guidelines', serializer.errors)
                error_msg = str(serializer.errors['guidelines']).lower()
                self.assertTrue('empty' in error_msg or 'blank' in error_msg or 'whitespace' in error_msg)
    
    def test_metadata_circular_reference_prevention(self):
        """Test metadata validation prevents circular references."""
        # Create a structure that would cause circular reference if not handled
        circular_dict = {'key': 'value'}
        circular_dict['self'] = circular_dict  # Circular reference
        
        data = {
            'guidelines': 'Test guidelines for circular reference prevention.',
            'metadata': circular_dict
        }
        
        serializer = JobCreateSerializer(data=data)
        # Should fail validation due to circular reference
        self.assertFalse(serializer.is_valid())
        self.assertIn('metadata', serializer.errors)