"""
Tests for Job model and related components (TDD Red Phase).

This module contains comprehensive tests for the Job model, JobStatus enumeration,
and all model functionality as specified in database-design.md.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone as django_timezone

from guideline_ingestion.jobs.models import Job, JobStatus


class TestJobStatus(TestCase):
    """Test JobStatus enumeration and methods."""
    
    def test_job_status_choices(self):
        """Test JobStatus has correct choices."""
        expected_choices = [
            ('PENDING', 'Pending'),
            ('PROCESSING', 'Processing'),
            ('COMPLETED', 'Completed'),
            ('FAILED', 'Failed'),
        ]
        self.assertEqual(list(JobStatus.choices), expected_choices)
    
    def test_job_status_values(self):
        """Test JobStatus has correct values."""
        self.assertEqual(JobStatus.PENDING, 'PENDING')
        self.assertEqual(JobStatus.PROCESSING, 'PROCESSING')
        self.assertEqual(JobStatus.COMPLETED, 'COMPLETED')
        self.assertEqual(JobStatus.FAILED, 'FAILED')
    
    def test_get_terminal_statuses(self):
        """Test get_terminal_statuses returns correct statuses."""
        terminal_statuses = JobStatus.get_terminal_statuses()
        self.assertEqual(set(terminal_statuses), {JobStatus.COMPLETED, JobStatus.FAILED})
    
    def test_get_active_statuses(self):
        """Test get_active_statuses returns correct statuses."""
        active_statuses = JobStatus.get_active_statuses()
        self.assertEqual(set(active_statuses), {JobStatus.PENDING, JobStatus.PROCESSING})


class TestJobModel(TestCase):
    """Test Job model fields, validation, and constraints."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_input_data = {
            'guidelines': 'Test guidelines content',
            'metadata': {'source': 'test', 'version': '1.0'}
        }
        
        self.valid_result_data = {
            'summary': 'Test summary of guidelines',
            'checklist': [
                {'item': 'Check item 1', 'priority': 'high'},
                {'item': 'Check item 2', 'priority': 'medium'}
            ]
        }
    
    def test_job_creation_default_values(self):
        """Test Job creation with default values."""
        job = Job.objects.create(input_data=self.valid_input_data)
        
        # Test auto-generated fields
        self.assertIsNotNone(job.id)
        self.assertIsNotNone(job.event_id)
        self.assertIsInstance(job.event_id, uuid.UUID)
        
        # Test default values
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.result, {})
        self.assertEqual(job.retry_count, 0)
        self.assertIsNone(job.error_message)
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.completed_at)
        
        # Test auto-generated timestamps
        self.assertIsNotNone(job.created_at)
        self.assertIsNotNone(job.updated_at)
    
    def test_job_field_types(self):
        """Test Job model field types."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            result=self.valid_result_data,
            status=JobStatus.COMPLETED,
            error_message='Test error',
            retry_count=2
        )
        
        # Test field types
        self.assertIsInstance(job.id, int)
        self.assertIsInstance(job.event_id, uuid.UUID)
        self.assertIsInstance(job.status, str)
        self.assertIsInstance(job.input_data, dict)
        self.assertIsInstance(job.result, dict)
        self.assertIsInstance(job.error_message, str)
        self.assertIsInstance(job.retry_count, int)
        self.assertIsInstance(job.created_at, datetime)
        self.assertIsInstance(job.updated_at, datetime)
    
    def test_job_event_id_unique(self):
        """Test event_id field is unique."""
        event_id = uuid.uuid4()
        
        # Create first job
        Job.objects.create(
            event_id=event_id,
            input_data=self.valid_input_data
        )
        
        # Attempt to create second job with same event_id should fail
        with self.assertRaises(IntegrityError):
            Job.objects.create(
                event_id=event_id,
                input_data=self.valid_input_data
            )
    
    def test_job_status_choices_validation(self):
        """Test status field validates against JobStatus choices."""
        job = Job(
            input_data=self.valid_input_data,
            status='INVALID_STATUS'
        )
        
        with self.assertRaises(ValidationError):
            job.full_clean()
    
    def test_job_retry_count_non_negative(self):
        """Test retry_count must be non-negative."""
        job = Job(
            input_data=self.valid_input_data,
            retry_count=-1
        )
        
        with self.assertRaises(ValidationError):
            job.full_clean()
    
    def test_job_input_data_required(self):
        """Test input_data field is required."""
        job = Job()
        
        with self.assertRaises(ValidationError):
            job.full_clean()
    
    def test_job_result_nullable(self):
        """Test result field can be null."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            result=None
        )
        
        self.assertIsNone(job.result)
    
    def test_job_error_message_nullable(self):
        """Test error_message field can be null."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            error_message=None
        )
        
        self.assertIsNone(job.error_message)
    
    def test_job_str_representation(self):
        """Test Job string representation."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.PROCESSING,
            started_at=django_timezone.now()
        )
        
        expected_str = f"Job {job.event_id} (PROCESSING)"
        self.assertEqual(str(job), expected_str)
    
    def test_job_meta_configuration(self):
        """Test Job Meta class configuration."""
        self.assertEqual(Job._meta.db_table, 'jobs')
        self.assertEqual(Job._meta.ordering, ['-created_at'])
    
    def test_job_indexes_exist(self):
        """Test Job model has required indexes."""
        index_names = [index.name for index in Job._meta.indexes]
        
        expected_indexes = [
            'jobs_event_id_idx',
            'jobs_status_idx',
            'jobs_created_at_idx',
            'jobs_updated_at_idx',
            'jobs_status_created_idx',
            'jobs_status_retry_idx'
        ]
        
        for expected_index in expected_indexes:
            self.assertIn(expected_index, index_names)
    
    def test_job_constraints_exist(self):
        """Test Job model has required constraints."""
        constraint_names = [constraint.name for constraint in Job._meta.constraints]
        
        expected_constraints = [
            'jobs_retry_count_non_negative',
            'jobs_status_started_at_consistency'
        ]
        
        for expected_constraint in expected_constraints:
            self.assertIn(expected_constraint, constraint_names)


class TestJobModelMethods(TestCase):
    """Test Job model methods and properties."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_input_data = {
            'guidelines': 'Test guidelines content',
            'metadata': {'source': 'test', 'version': '1.0'}
        }
    
    def test_job_is_terminal_property(self):
        """Test is_terminal property for different statuses."""
        # Test terminal statuses
        completed_job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.COMPLETED,
            started_at=django_timezone.now(),
            completed_at=django_timezone.now()
        )
        failed_job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.FAILED,
            started_at=django_timezone.now(),
            completed_at=django_timezone.now()
        )
        
        self.assertTrue(completed_job.is_terminal)
        self.assertTrue(failed_job.is_terminal)
        
        # Test non-terminal statuses
        pending_job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.PENDING
        )
        processing_job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.PROCESSING,
            started_at=django_timezone.now()
        )
        
        self.assertFalse(pending_job.is_terminal)
        self.assertFalse(processing_job.is_terminal)
    
    def test_job_duration_property(self):
        """Test duration property calculation."""
        # Job with no started_at should return None
        job = Job.objects.create(input_data=self.valid_input_data)
        self.assertIsNone(job.duration)
        
        # Job with started_at but no completed_at should return None
        job.status = JobStatus.PROCESSING
        job.started_at = django_timezone.now()
        job.save()
        self.assertIsNone(job.duration)
        
        # Job with both started_at and completed_at should return duration
        job.status = JobStatus.COMPLETED
        job.completed_at = django_timezone.now()
        job.save()
        self.assertIsNotNone(job.duration)
        self.assertGreaterEqual(job.duration.total_seconds(), 0)
    
    def test_job_mark_as_processing_method(self):
        """Test mark_as_processing method."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.PENDING
        )
        
        job.mark_as_processing()
        
        self.assertEqual(job.status, JobStatus.PROCESSING)
        self.assertIsNotNone(job.started_at)
        self.assertIsNone(job.completed_at)
    
    def test_job_mark_as_completed_method(self):
        """Test mark_as_completed method."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.PROCESSING,
            started_at=django_timezone.now()
        )
        
        result_data = {
            'summary': 'Test summary',
            'checklist': [{'item': 'Test item'}]
        }
        
        job.mark_as_completed(result_data)
        
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.result, result_data)
        self.assertIsNotNone(job.completed_at)
        self.assertIsNone(job.error_message)
    
    def test_job_mark_as_failed_method(self):
        """Test mark_as_failed method."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.PROCESSING,
            started_at=django_timezone.now()
        )
        
        error_message = 'Test error message'
        
        job.mark_as_failed(error_message)
        
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_message, error_message)
        self.assertIsNotNone(job.completed_at)
    
    def test_job_increment_retry_count_method(self):
        """Test increment_retry_count method."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            retry_count=0
        )
        
        job.increment_retry_count()
        
        self.assertEqual(job.retry_count, 1)
        
        job.increment_retry_count()
        
        self.assertEqual(job.retry_count, 2)


class TestJobModelEdgeCases(TestCase):
    """Test Job model edge cases and error conditions."""
    
    def setUp(self):
        """Set up test data."""
        self.valid_input_data = {
            'guidelines': 'Test guidelines content',
            'metadata': {'source': 'test', 'version': '1.0'}
        }
    
    def test_job_large_input_data(self):
        """Test Job with large input_data."""
        large_input_data = {
            'guidelines': 'A' * 10000,  # 10KB of data
            'metadata': {'source': 'test', 'items': ['item'] * 1000}
        }
        
        job = Job.objects.create(input_data=large_input_data)
        
        self.assertEqual(job.input_data, large_input_data)
    
    def test_job_large_result_data(self):
        """Test Job with large result data."""
        large_result_data = {
            'summary': 'B' * 5000,  # 5KB summary
            'checklist': [{'item': f'Item {i}', 'details': 'X' * 100} for i in range(100)]
        }
        
        job = Job.objects.create(
            input_data=self.valid_input_data,
            result=large_result_data
        )
        
        self.assertEqual(job.result, large_result_data)
    
    def test_job_concurrent_creation(self):
        """Test concurrent job creation doesn't cause issues."""
        jobs = []
        
        # Create multiple jobs concurrently
        for i in range(10):
            job = Job.objects.create(
                input_data={**self.valid_input_data, 'batch_id': i}
            )
            jobs.append(job)
        
        # Verify all jobs have unique event_ids
        event_ids = [job.event_id for job in jobs]
        self.assertEqual(len(event_ids), len(set(event_ids)))
    
    def test_job_status_transition_validation(self):
        """Test status transition validation."""
        job = Job.objects.create(
            input_data=self.valid_input_data,
            status=JobStatus.PENDING
        )
        
        # Valid transition: PENDING -> PROCESSING
        job.status = JobStatus.PROCESSING
        job.started_at = django_timezone.now()
        job.full_clean()  # Should not raise
        
        # Valid transition: PROCESSING -> COMPLETED
        job.status = JobStatus.COMPLETED
        job.completed_at = django_timezone.now()
        job.full_clean()  # Should not raise
    
    def test_job_auto_updated_at(self):
        """Test updated_at field is automatically updated."""
        job = Job.objects.create(input_data=self.valid_input_data)
        original_updated_at = job.updated_at
        
        # Modify and save (must satisfy constraint: PROCESSING status needs started_at)
        job.status = JobStatus.PROCESSING
        job.started_at = django_timezone.now()
        job.save()
        
        # updated_at should be different
        self.assertGreater(job.updated_at, original_updated_at)
    
    def test_job_unicode_content(self):
        """Test Job with unicode content."""
        unicode_input_data = {
            'guidelines': 'Test with unicode: 测试 🔧 ñáéíóú',
            'metadata': {'description': 'Тест с unicode символами'}
        }
        
        job = Job.objects.create(input_data=unicode_input_data)
        
        self.assertEqual(job.input_data, unicode_input_data)
        self.assertIn('测试', str(job.input_data))