"""
End-to-end tests for GPT integration with Celery tasks.

Tests the complete flow: API → Celery Task → GPT Processing → Database Storage
"""

from unittest.mock import patch
from django.test import TestCase

from guideline_ingestion.jobs.models import Job, JobStatus
from guideline_ingestion.jobs.tasks import process_guideline_job


class TestEndToEndGPTIntegration(TestCase):
    """Test complete end-to-end GPT integration."""
    
    def setUp(self):
        """Set up test data."""
        self.test_guidelines = """
        API Security Guidelines:
        1. Use HTTPS for all endpoints
        2. Implement authentication and authorization
        3. Validate all input data
        4. Use rate limiting
        5. Log security events
        """
        
        self.job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data={'guidelines': self.test_guidelines}
        )
    
    @patch('guideline_ingestion.jobs.tasks.process_guidelines_with_gpt')
    def test_end_to_end_processing_success(self, mock_gpt_process):
        """Test complete end-to-end processing with GPT integration."""
        # Mock GPT processing response
        mock_gpt_response = {
            'summary': 'API security guidelines covering HTTPS, authentication, validation, rate limiting, and logging.',
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
                    'title': 'Add authentication',
                    'description': 'Implement proper authentication mechanisms',
                    'priority': 'high',
                    'category': 'security'
                },
                {
                    'id': 3,
                    'title': 'Validate input',
                    'description': 'Implement thorough input validation',
                    'priority': 'medium',
                    'category': 'validation'
                }
            ]
        }
        mock_gpt_process.return_value = mock_gpt_response
        
        # Execute the task
        result = process_guideline_job(self.job.id, self.test_guidelines)
        
        # Verify task result
        self.assertEqual(result, mock_gpt_response)
        
        # Verify job was updated correctly
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.COMPLETED)
        self.assertEqual(self.job.result, mock_gpt_response)
        self.assertIsNotNone(self.job.started_at)
        self.assertIsNotNone(self.job.completed_at)
        self.assertIsNone(self.job.error_message)
        
        # Verify GPT processing was called with correct input
        mock_gpt_process.assert_called_once_with(self.test_guidelines)
        
        # Verify result structure
        self.assertIn('summary', self.job.result)
        self.assertIn('checklist', self.job.result)
        
        # Verify summary
        summary = self.job.result['summary']
        self.assertIsInstance(summary, str)
        self.assertIn('API security', summary)
        
        # Verify checklist structure
        checklist = self.job.result['checklist']
        self.assertIsInstance(checklist, list)
        self.assertEqual(len(checklist), 3)
        
        for item in checklist:
            self.assertIn('id', item)
            self.assertIn('title', item) 
            self.assertIn('description', item)
            self.assertIn('priority', item)
            self.assertIn('category', item)
    
    def test_end_to_end_gpt_configuration(self):
        """Test that GPT configuration is properly loaded from settings."""
        from django.conf import settings
        
        # Verify OpenAI configuration is available
        self.assertIsNotNone(settings.OPENAI_API_KEY)
        self.assertEqual(settings.OPENAI_MODEL, 'gpt-4')
        self.assertEqual(settings.OPENAI_MAX_TOKENS, 2000)
        self.assertEqual(settings.OPENAI_TEMPERATURE, 0.1)
        self.assertEqual(settings.OPENAI_RATE_LIMIT_REQUESTS, 60)
        self.assertEqual(settings.OPENAI_RATE_LIMIT_WINDOW, 60)