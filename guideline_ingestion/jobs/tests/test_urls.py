"""
Tests for jobs URL routing (TDD Red Phase).

This module contains tests for URL pattern matching, parameter extraction,
and routing configuration.
"""

import uuid

import pytest
from django.test import TestCase
from django.urls import reverse, resolve, NoReverseMatch

from guideline_ingestion.jobs.views import JobCreateView, JobRetrieveView


class TestJobURLPatterns(TestCase):
    """Test URL pattern matching and resolution."""
    
    def test_job_create_url_pattern(self):
        """Test POST /jobs/ URL pattern resolution."""
        url = reverse('jobs:job-create')
        
        self.assertEqual(url, '/jobs/')
        
        # Test URL resolution
        resolved = resolve(url)
        self.assertEqual(resolved.view_name, 'jobs:job-create')
        self.assertEqual(resolved.func.view_class, JobCreateView)
    
    def test_job_retrieve_url_pattern(self):
        """Test GET /jobs/{event_id}/ URL pattern resolution."""
        event_id = uuid.uuid4()
        url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        
        expected_url = f'/jobs/{event_id}/'
        self.assertEqual(url, expected_url)
        
        # Test URL resolution
        resolved = resolve(url)
        self.assertEqual(resolved.view_name, 'jobs:job-retrieve')
        self.assertEqual(resolved.func.view_class, JobRetrieveView)
        self.assertEqual(resolved.kwargs['event_id'], event_id)
    
    def test_job_retrieve_url_uuid_validation(self):
        """Test that job retrieve URL validates UUID format."""
        event_id = uuid.uuid4()
        url = f'/jobs/{event_id}/'
        
        # Valid UUID should resolve
        resolved = resolve(url)
        self.assertEqual(resolved.view_name, 'jobs:job-retrieve')
        self.assertEqual(resolved.kwargs['event_id'], event_id)
    
    def test_job_retrieve_url_invalid_uuid_format(self):
        """Test that invalid UUID format doesn't match URL pattern."""
        invalid_ids = [
            'not-a-uuid',
            '12345',
            'invalid-uuid-format',
            '550e8400-e29b-41d4-a716',  # Incomplete UUID
            '550e8400-e29b-41d4-a716-446655440000-extra'  # Too long
        ]
        
        for invalid_id in invalid_ids:
            url = f'/jobs/{invalid_id}/'
            
            with self.assertRaises(Exception):  # Should not resolve
                resolve(url)
    
    def test_job_create_url_reverse_lookup(self):
        """Test reverse URL lookup for job creation."""
        url = reverse('jobs:job-create')
        self.assertEqual(url, '/jobs/')
    
    def test_job_retrieve_url_reverse_lookup(self):
        """Test reverse URL lookup for job retrieval."""
        event_id = uuid.uuid4()
        url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        
        expected_url = f'/jobs/{event_id}/'
        self.assertEqual(url, expected_url)
    
    def test_job_retrieve_url_reverse_lookup_string_uuid(self):
        """Test reverse URL lookup with string UUID."""
        event_id = str(uuid.uuid4())
        url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        
        expected_url = f'/jobs/{event_id}/'
        self.assertEqual(url, expected_url)
    
    def test_job_retrieve_url_reverse_lookup_invalid_uuid(self):
        """Test reverse URL lookup fails with invalid UUID."""
        with self.assertRaises(NoReverseMatch):
            reverse('jobs:job-retrieve', kwargs={'event_id': 'invalid-uuid'})
    
    def test_trailing_slash_handling(self):
        """Test that URLs handle trailing slashes correctly."""
        # Job create URL
        create_url = reverse('jobs:job-create')
        self.assertTrue(create_url.endswith('/'))
        
        # Job retrieve URL
        event_id = uuid.uuid4()
        retrieve_url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        self.assertTrue(retrieve_url.endswith('/'))
    
    def test_url_namespace(self):
        """Test that URLs are properly namespaced."""
        # Test that we can access URLs through jobs namespace
        create_url = reverse('jobs:job-create')
        self.assertIsNotNone(create_url)
        
        event_id = uuid.uuid4()
        retrieve_url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        self.assertIsNotNone(retrieve_url)
    
    def test_url_names_uniqueness(self):
        """Test that URL names are unique within namespace."""
        # This test ensures we don't have naming conflicts
        create_url = reverse('jobs:job-create')
        
        event_id = uuid.uuid4()
        retrieve_url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        
        self.assertNotEqual(create_url, retrieve_url)


class TestURLParameterExtraction(TestCase):
    """Test URL parameter extraction and validation."""
    
    def test_event_id_parameter_extraction(self):
        """Test that event_id parameter is correctly extracted."""
        event_id = uuid.uuid4()
        url = f'/jobs/{event_id}/'
        
        resolved = resolve(url)
        
        self.assertIn('event_id', resolved.kwargs)
        self.assertEqual(resolved.kwargs['event_id'], event_id)
    
    def test_event_id_parameter_type(self):
        """Test that event_id parameter is extracted as string."""
        event_id = uuid.uuid4()
        url = f'/jobs/{event_id}/'
        
        resolved = resolve(url)
        
        extracted_id = resolved.kwargs['event_id']
        self.assertIsInstance(extracted_id, uuid.UUID)
        
        # Verify it matches the original UUID
        self.assertEqual(extracted_id, event_id)
    
    def test_multiple_uuid_formats(self):
        """Test URL handling of different UUID string formats."""
        # Standard UUID format
        standard_uuid = uuid.uuid4()
        url = f'/jobs/{standard_uuid}/'
        
        resolved = resolve(url)
        self.assertEqual(resolved.kwargs['event_id'], standard_uuid)
        
        # UUID without hyphens should not match (strict format)
        uuid_no_hyphens = str(standard_uuid).replace('-', '')
        url_no_hyphens = f'/jobs/{uuid_no_hyphens}/'
        
        with self.assertRaises(Exception):
            resolve(url_no_hyphens)


class TestURLIntegration(TestCase):
    """Test URL integration with the broader application."""
    
    def test_urls_included_in_main_urlconf(self):
        """Test that job URLs are properly included in main URL configuration."""
        # This test ensures our URLs are accessible from the main application
        try:
            create_url = reverse('jobs:job-create')
            self.assertIsNotNone(create_url)
        except NoReverseMatch:
            self.fail("jobs:job-create URL not found - check URL inclusion")
        
        try:
            event_id = uuid.uuid4()
            retrieve_url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
            self.assertIsNotNone(retrieve_url)
        except NoReverseMatch:
            self.fail("jobs:job-retrieve URL not found - check URL inclusion")
    
    def test_url_conflicts_with_other_apps(self):
        """Test that job URLs don't conflict with other application URLs."""
        # Create URL and retrieve URL should not conflict
        create_url = reverse('jobs:job-create')
        
        event_id = uuid.uuid4()
        retrieve_url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        
        self.assertNotEqual(create_url, retrieve_url)
        
        # URLs should be under /jobs/ prefix
        self.assertTrue(create_url.startswith('/jobs/'))
        self.assertTrue(retrieve_url.startswith('/jobs/'))
    
    def test_url_patterns_order(self):
        """Test that URL patterns are in correct order for proper matching."""
        # More specific patterns (with parameters) should come after general ones
        # /jobs/ should be matched before /jobs/{event_id}/
        
        create_url = '/jobs/'
        resolved_create = resolve(create_url)
        self.assertEqual(resolved_create.view_name, 'jobs:job-create')
        
        # UUID pattern should not match the general /jobs/ pattern
        event_id = uuid.uuid4()
        retrieve_url = f'/jobs/{event_id}/'
        resolved_retrieve = resolve(retrieve_url)
        self.assertEqual(resolved_retrieve.view_name, 'jobs:job-retrieve')


class TestURLEdgeCases(TestCase):
    """Test edge cases and error conditions in URL routing."""
    
    def test_empty_event_id(self):
        """Test handling of empty event_id in URL."""
        url = '/jobs//'
        
        with self.assertRaises(Exception):
            resolve(url)
    
    def test_malformed_uuid_variants(self):
        """Test various malformed UUID formats."""
        malformed_uuids = [
            '550e8400-e29b-41d4-a716-44665544000',   # Missing digit
            '550e8400-e29b-41d4-a716-44665544000g',  # Invalid character
            '550e8400-e29b-41d4-a716-446655440000-', # Trailing hyphen
            '-550e8400-e29b-41d4-a716-446655440000', # Leading hyphen
            '550e8400-e29b-41d4-a716-446655440000 ', # Trailing space
            ' 550e8400-e29b-41d4-a716-446655440000', # Leading space
        ]
        
        for malformed_uuid in malformed_uuids:
            url = f'/jobs/{malformed_uuid}/'
            
            with self.assertRaises(Exception):
                resolve(url)
    
    def test_case_sensitivity(self):
        """Test UUID case sensitivity in URLs."""
        # Standard lowercase UUID
        event_id = uuid.uuid4()
        url_lower = f'/jobs/{str(event_id).lower()}/'
        
        resolved = resolve(url_lower)
        self.assertEqual(resolved.view_name, 'jobs:job-retrieve')
        
        # Uppercase UUID should also work
        url_upper = f'/jobs/{str(event_id).upper()}/'
        
        resolved_upper = resolve(url_upper)
        self.assertEqual(resolved_upper.view_name, 'jobs:job-retrieve')
    
    def test_url_special_characters(self):
        """Test URL handling with special characters that might be confused with UUIDs."""
        special_cases = [
            '00000000-0000-0000-0000-000000000000',  # All zeros
            'ffffffff-ffff-ffff-ffff-ffffffffffff',  # All f's
            'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF',  # All F's uppercase
        ]
        
        for special_uuid in special_cases:
            url = f'/jobs/{special_uuid}/'
            
            # These should resolve successfully as they are valid UUIDs
            resolved = resolve(url)
            self.assertEqual(resolved.view_name, 'jobs:job-retrieve')
            self.assertEqual(str(resolved.kwargs['event_id']), special_uuid.lower())


class TestURLPermissions(TestCase):
    """Test URL-level permissions and access control."""
    
    def test_job_create_url_public_access(self):
        """Test that job creation URL is publicly accessible."""
        # This test ensures the URL pattern itself doesn't impose restrictions
        url = reverse('jobs:job-create')
        resolved = resolve(url)
        
        # URL should resolve without authentication requirements at URL level
        self.assertEqual(resolved.view_name, 'jobs:job-create')
    
    def test_job_retrieve_url_public_access(self):
        """Test that job retrieval URL is publicly accessible."""
        event_id = uuid.uuid4()
        url = reverse('jobs:job-retrieve', kwargs={'event_id': event_id})
        resolved = resolve(url)
        
        # URL should resolve without authentication requirements at URL level
        self.assertEqual(resolved.view_name, 'jobs:job-retrieve')
        self.assertEqual(resolved.kwargs['event_id'], event_id)