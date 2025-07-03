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
        # Default is handled at the model level or view level
        self.assertNotIn('priority', serializer.validated_data)
    
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
        # Create metadata > 1KB
        large_metadata = {f'key_{i}': 'x' * 100 for i in range(15)}
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
        
        # Create jobs with different statuses
        for i, status in enumerate([JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.COMPLETED]):
            job = Job.objects.create(
                status=status,
                input_data={'guidelines': f'Test guidelines {i}'},
                created_at=timezone.now() - timedelta(minutes=i)
            )
            self.jobs.append(job)
    
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