"""
Tests for GPT integration and OpenAI API client functionality (TDD Red Phase).

This module contains comprehensive tests for the two-step GPT chain:
1. Summarization of input guidelines 
2. Checklist generation from summary

Tests include mocked OpenAI API responses, error handling, rate limiting,
and response parsing validation.
"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

import pytest
from django.test import TestCase
from rest_framework.test import APITestCase
from openai import OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from guideline_ingestion.jobs.gpt_client import (
    GPTClient,
    RateLimiter,
    GPTClientError,
    GPTRateLimitError,
    GPTValidationError,
    SummarizationError,
    ChecklistGenerationError,
)


class TestGPTClient(TestCase):
    """Test GPT client initialization and configuration."""
    
    def setUp(self):
        """Set up test client."""
        self.api_key = "test-api-key-123"
        self.client = GPTClient(api_key=self.api_key)
    
    def test_gpt_client_initialization(self):
        """Test GPT client initializes with correct configuration."""
        self.assertEqual(self.client.api_key, self.api_key)
        self.assertEqual(self.client.model, "gpt-4")
        self.assertEqual(self.client.max_tokens, 2000)
        self.assertEqual(self.client.temperature, 0.1)
        self.assertIsInstance(self.client.openai_client, OpenAI)
    
    def test_gpt_client_custom_configuration(self):
        """Test GPT client with custom configuration."""
        client = GPTClient(
            api_key=self.api_key,
            model="gpt-3.5-turbo",
            max_tokens=1500,
            temperature=0.5
        )
        
        self.assertEqual(client.model, "gpt-3.5-turbo")
        self.assertEqual(client.max_tokens, 1500)
        self.assertEqual(client.temperature, 0.5)
    
    def test_gpt_client_missing_api_key(self):
        """Test GPT client raises error with missing API key."""
        with self.assertRaises(GPTClientError):
            GPTClient(api_key="")
        
        with self.assertRaises(GPTClientError):
            GPTClient(api_key=None)


class TestSummarization(TestCase):
    """Test guidelines summarization functionality."""
    
    def setUp(self):
        """Set up test client and sample data."""
        self.client = GPTClient(api_key="test-api-key")
        self.sample_guidelines = """
        Security Guidelines for API Development:
        1. Always use HTTPS for API endpoints to encrypt data in transit
        2. Implement proper authentication and authorization mechanisms
        3. Validate all input data thoroughly to prevent injection attacks
        4. Use rate limiting to prevent abuse and DDoS attacks
        5. Log security events for monitoring and incident response
        6. Implement proper error handling without exposing sensitive information
        7. Use secure coding practices and regular security audits
        8. Keep dependencies updated to patch known vulnerabilities
        """
        
        self.expected_summary = """
        These security guidelines focus on API development best practices including:
        - HTTPS encryption for secure data transmission
        - Authentication and authorization for access control
        - Input validation to prevent security vulnerabilities
        - Rate limiting for abuse prevention
        - Security monitoring and logging
        - Secure error handling and coding practices
        - Regular security maintenance and updates
        """
    
    @patch.object(GPTClient, '_make_api_call')
    def test_summarize_guidelines_success(self, mock_api_call):
        """Test successful guidelines summarization."""
        # Mock API call response
        mock_api_call.return_value = self.expected_summary.strip()
        
        # Execute summarization
        result = self.client.summarize_guidelines(self.sample_guidelines)
        
        # Verify result
        self.assertIsInstance(result, str)
        self.assertIn("security guidelines", result.lower())
        self.assertIn("https", result.lower())
        self.assertIn("authentication", result.lower())
        
        # Verify API call was made
        mock_api_call.assert_called_once()
        call_args = mock_api_call.call_args[0]
        
        # Verify the messages structure passed to API call
        messages = call_args[0]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn('summarize', messages[0]['content'].lower())
        self.assertEqual(messages[1]['content'], self.sample_guidelines)
    
    def test_summarize_guidelines_empty_input(self):
        """Test summarization with empty input."""
        with self.assertRaises(GPTValidationError) as context:
            self.client.summarize_guidelines("")
        
        self.assertIn("Guidelines cannot be empty", str(context.exception))
        
        with self.assertRaises(GPTValidationError):
            self.client.summarize_guidelines("   ")
        
        with self.assertRaises(GPTValidationError):
            self.client.summarize_guidelines(None)
    
    def test_summarize_guidelines_too_long(self):
        """Test summarization with input that's too long."""
        # Create very long input (> 10000 characters)
        long_guidelines = "Security guideline: " * 600  # >10000 characters
        
        with self.assertRaises(GPTValidationError) as context:
            self.client.summarize_guidelines(long_guidelines)
        
        self.assertIn("Guidelines too long", str(context.exception))
    
    @patch.object(GPTClient, '_make_api_call')
    def test_summarize_guidelines_rate_limit_error(self, mock_api_call):
        """Test summarization with rate limit error."""
        mock_api_call.side_effect = GPTRateLimitError("Rate limit exceeded")
        
        with self.assertRaises(GPTRateLimitError) as context:
            self.client.summarize_guidelines(self.sample_guidelines)
        
        self.assertIn("Rate limit exceeded", str(context.exception))
    
    @patch.object(GPTClient, '_make_api_call')
    def test_summarize_guidelines_api_error(self, mock_api_call):
        """Test summarization with general API error."""
        mock_api_call.side_effect = SummarizationError("API error occurred")
        
        with self.assertRaises(SummarizationError) as context:
            self.client.summarize_guidelines(self.sample_guidelines)
        
        self.assertIn("Failed to summarize guidelines", str(context.exception))
    
    @patch.object(GPTClient, '_make_api_call')
    def test_summarize_guidelines_empty_response(self, mock_api_call):
        """Test summarization with empty response from OpenAI."""
        mock_api_call.return_value = ""
        
        with self.assertRaises(SummarizationError) as context:
            self.client.summarize_guidelines(self.sample_guidelines)
        
        self.assertIn("Empty response", str(context.exception))


class TestChecklistGeneration(TestCase):
    """Test checklist generation from summary."""
    
    def setUp(self):
        """Set up test client and sample data."""
        self.client = GPTClient(api_key="test-api-key")
        self.sample_summary = """
        These security guidelines focus on API development best practices including:
        - HTTPS encryption for secure data transmission
        - Authentication and authorization for access control
        - Input validation to prevent security vulnerabilities
        - Rate limiting for abuse prevention
        - Security monitoring and logging
        """
        
        self.expected_checklist = [
            {
                "id": 1,
                "title": "Implement HTTPS encryption",
                "description": "Ensure all API endpoints use HTTPS for secure data transmission",
                "priority": "high",
                "category": "security"
            },
            {
                "id": 2,
                "title": "Add authentication and authorization",
                "description": "Implement proper access control mechanisms",
                "priority": "high",
                "category": "security"
            },
            {
                "id": 3,
                "title": "Validate input data",
                "description": "Implement thorough input validation to prevent vulnerabilities",
                "priority": "high",
                "category": "validation"
            },
            {
                "id": 4,
                "title": "Implement rate limiting",
                "description": "Add rate limiting to prevent abuse and DDoS attacks",
                "priority": "medium",
                "category": "performance"
            }
        ]
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_success(self, mock_api_call):
        """Test successful checklist generation."""
        # Mock API call response with valid JSON
        mock_api_call.return_value = json.dumps(self.expected_checklist)
        
        # Execute checklist generation
        result = self.client.generate_checklist(self.sample_summary)
        
        # Verify result structure
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 4)
        
        # Verify each checklist item structure
        for item in result:
            self.assertIn('id', item)
            self.assertIn('title', item)
            self.assertIn('description', item)
            self.assertIn('priority', item)
            self.assertIn('category', item)
            
            self.assertIsInstance(item['id'], int)
            self.assertIsInstance(item['title'], str)
            self.assertIsInstance(item['description'], str)
            self.assertIn(item['priority'], ['high', 'medium', 'low'])
            self.assertIsInstance(item['category'], str)
        
        # Verify API call was made
        mock_api_call.assert_called_once()
        call_args = mock_api_call.call_args[0]
        
        # Verify the messages structure passed to API call
        messages = call_args[0]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn('checklist', messages[0]['content'].lower())
        self.assertIn('json', messages[0]['content'].lower())
    
    def test_generate_checklist_empty_summary(self):
        """Test checklist generation with empty summary."""
        with self.assertRaises(GPTValidationError):
            self.client.generate_checklist("")
        
        with self.assertRaises(GPTValidationError):
            self.client.generate_checklist("   ")
        
        with self.assertRaises(GPTValidationError):
            self.client.generate_checklist(None)
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_invalid_json(self, mock_api_call):
        """Test checklist generation with invalid JSON response."""
        mock_api_call.return_value = "Invalid JSON response from GPT"
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist(self.sample_summary)
        
        self.assertIn("Invalid JSON", str(context.exception))
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_invalid_structure(self, mock_api_call):
        """Test checklist generation with invalid checklist structure."""
        # Invalid checklist - missing required fields
        invalid_checklist = [
            {"title": "Missing required fields"},
            {"id": 2, "description": "Missing title"}
        ]
        
        mock_api_call.return_value = json.dumps(invalid_checklist)
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist(self.sample_summary)
        
        self.assertIn("Invalid checklist item", str(context.exception))


class TestGPTChainIntegration(TestCase):
    """Test complete two-step GPT chain integration."""
    
    def setUp(self):
        """Set up test client and sample data."""
        self.client = GPTClient(api_key="test-api-key")
        self.sample_guidelines = """
        Security Guidelines for API Development:
        1. Always use HTTPS for API endpoints
        2. Implement proper authentication and authorization
        3. Validate all input data thoroughly
        4. Use rate limiting to prevent abuse
        5. Log security events for monitoring
        """
    
    @patch.object(GPTClient, '_make_api_call')
    def test_process_guidelines_complete_chain(self, mock_api_call):
        """Test complete two-step GPT processing chain."""
        # Mock responses for both steps
        summary_text = "API security guidelines covering HTTPS, authentication, validation, rate limiting, and monitoring."
        
        checklist_data = [
            {
                "id": 1,
                "title": "Implement HTTPS",
                "description": "Ensure all API endpoints use HTTPS encryption",
                "priority": "high",
                "category": "security"
            },
            {
                "id": 2,
                "title": "Add authentication",
                "description": "Implement proper authentication mechanisms",
                "priority": "high",
                "category": "security"
            }
        ]
        
        # First call returns summary, second call returns checklist JSON
        mock_api_call.side_effect = [summary_text, json.dumps(checklist_data)]
        
        # Execute complete chain
        result = self.client.process_guidelines(self.sample_guidelines)
        
        # Verify result structure
        self.assertIsInstance(result, dict)
        self.assertIn('summary', result)
        self.assertIn('checklist', result)
        
        # Verify summary
        self.assertIsInstance(result['summary'], str)
        self.assertIn("API security", result['summary'])
        
        # Verify checklist
        self.assertIsInstance(result['checklist'], list)
        self.assertEqual(len(result['checklist']), 2)
        
        # Verify API was called twice (summary + checklist)
        self.assertEqual(mock_api_call.call_count, 2)
    
    def test_process_guidelines_empty_input(self):
        """Test complete chain with empty input."""
        with self.assertRaises(GPTValidationError):
            self.client.process_guidelines("")
    
    @patch.object(GPTClient, '_make_api_call')
    def test_process_guidelines_summarization_failure(self, mock_api_call):
        """Test complete chain when summarization fails."""
        mock_api_call.side_effect = SummarizationError("API error")
        
        with self.assertRaises(SummarizationError):
            self.client.process_guidelines(self.sample_guidelines)
    
    @patch.object(GPTClient, '_make_api_call')
    def test_process_guidelines_checklist_failure(self, mock_api_call):
        """Test complete chain when checklist generation fails."""
        # First call (summary) succeeds, second call (checklist) fails
        mock_api_call.side_effect = [
            "Summary of guidelines",
            ChecklistGenerationError("API error")
        ]
        
        with self.assertRaises(ChecklistGenerationError):
            self.client.process_guidelines(self.sample_guidelines)


class TestRateLimiting(TestCase):
    """Test rate limiting functionality."""
    
    def setUp(self):
        """Set up test client."""
        self.client = GPTClient(api_key="test-api-key")
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter is properly initialized."""
        self.assertIsNotNone(self.client.rate_limiter)
        self.assertEqual(self.client.rate_limiter.max_requests, 60)  # Default: 60 requests per minute
        self.assertEqual(self.client.rate_limiter.time_window, 60)   # 60 seconds
    
    def test_rate_limiter_custom_limits(self):
        """Test rate limiter with custom limits."""
        client = GPTClient(
            api_key="test-api-key",
            rate_limit_requests=30,
            rate_limit_window=120
        )
        
        self.assertEqual(client.rate_limiter.max_requests, 30)
        self.assertEqual(client.rate_limiter.time_window, 120)
    
    @patch.object(GPTClient, '_check_rate_limit')
    def test_rate_limit_exceeded(self, mock_check_rate_limit):
        """Test behavior when rate limit is exceeded."""
        # Mock rate limit check to raise exception
        mock_check_rate_limit.side_effect = GPTRateLimitError("Rate limit exceeded. Try again in 60.00 seconds")
        
        client = GPTClient(api_key="test-api-key")
        
        # This call should be rate limited
        with self.assertRaises(GPTRateLimitError) as context:
            client.summarize_guidelines("Test guidelines")
        
        self.assertIn("Rate limit exceeded", str(context.exception))


class TestResponseValidation(TestCase):
    """Test response parsing and validation."""
    
    def setUp(self):
        """Set up test client."""
        self.client = GPTClient(api_key="test-api-key")
    
    def test_validate_checklist_item_valid(self):
        """Test validation of valid checklist item."""
        valid_item = {
            "id": 1,
            "title": "Test item",
            "description": "Test description",
            "priority": "high",
            "category": "security"
        }
        
        # Should not raise any exception
        self.client._validate_checklist_item(valid_item)
    
    def test_validate_checklist_item_missing_fields(self):
        """Test validation of checklist item with missing fields."""
        invalid_items = [
            {"title": "Missing id"},
            {"id": 1, "description": "Missing title"},
            {"id": 1, "title": "Missing description"},
            {"id": 1, "title": "Test", "description": "Missing priority"},
            {"id": 1, "title": "Test", "description": "Test", "priority": "high"}  # Missing category
        ]
        
        for item in invalid_items:
            with self.assertRaises(ChecklistGenerationError):
                self.client._validate_checklist_item(item)
    
    def test_validate_checklist_item_invalid_types(self):
        """Test validation of checklist item with invalid types."""
        invalid_items = [
            {"id": "not_int", "title": "Test", "description": "Test", "priority": "high", "category": "test"},
            {"id": 1, "title": 123, "description": "Test", "priority": "high", "category": "test"},
            {"id": 1, "title": "Test", "description": 456, "priority": "high", "category": "test"},
            {"id": 1, "title": "Test", "description": "Test", "priority": "invalid", "category": "test"},
            {"id": 1, "title": "Test", "description": "Test", "priority": "high", "category": 789}
        ]
        
        for item in invalid_items:
            with self.assertRaises(ChecklistGenerationError):
                self.client._validate_checklist_item(item)
    
    def test_validate_summary_valid(self):
        """Test validation of valid summary."""
        valid_summaries = [
            "This is a valid summary.",
            "A longer summary with multiple sentences. It contains useful information.",
            "Summary with numbers: 1, 2, 3 and special characters!@#"
        ]
        
        for summary in valid_summaries:
            # Should not raise any exception
            self.client._validate_summary(summary)
    
    def test_validate_summary_invalid(self):
        """Test validation of invalid summary."""
        invalid_summaries = [
            "",  # Empty
            "   ",  # Whitespace only
            "x",  # Too short
            "a" * 5000  # Too long
        ]
        
        for summary in invalid_summaries:
            with self.assertRaises(SummarizationError):
                self.client._validate_summary(summary)


class TestRateLimiterImplementation(TestCase):
    """Test comprehensive rate limiter functionality."""
    
    def setUp(self):
        """Set up test rate limiter."""
        from guideline_ingestion.jobs.gpt_client import RateLimiter
        self.rate_limiter = RateLimiter(max_requests=3, time_window=60)
    
    def test_rate_limiter_can_make_request_initial(self):
        """Test rate limiter allows initial requests."""
        self.assertTrue(self.rate_limiter.can_make_request())
    
    def test_rate_limiter_tracks_requests(self):
        """Test rate limiter properly tracks requests."""
        # Make requests up to the limit
        for i in range(3):
            self.assertTrue(self.rate_limiter.can_make_request())
            self.rate_limiter.record_request()
        
        # Should be at limit now
        self.assertFalse(self.rate_limiter.can_make_request())
    
    def test_rate_limiter_wait_time_calculation(self):
        """Test rate limiter calculates correct wait time."""
        # Fill up the rate limiter
        for i in range(3):
            self.rate_limiter.record_request()
        
        # Should need to wait
        wait_time = self.rate_limiter.wait_time()
        self.assertGreater(wait_time, 0)
        self.assertLessEqual(wait_time, 60)  # Within time window
    
    def test_rate_limiter_wait_time_empty(self):
        """Test rate limiter returns zero wait time when empty."""
        wait_time = self.rate_limiter.wait_time()
        self.assertEqual(wait_time, 0.0)
    
    def test_rate_limiter_request_cleanup(self):
        """Test rate limiter cleans up old requests."""
        from datetime import datetime, timedelta
        
        # Manually add old request
        old_time = datetime.now() - timedelta(seconds=70)  # Older than time window
        self.rate_limiter.requests.append(old_time)
        
        # Should be cleaned up when checking
        self.assertTrue(self.rate_limiter.can_make_request())
        self.assertEqual(len(self.rate_limiter.requests), 0)


class TestGPTClientAPICallErrorHandling(TestCase):
    """Test GPT client API call error handling scenarios."""
    
    def setUp(self):
        """Set up test client."""
        self.client = GPTClient(api_key="test-api-key")
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_api_call_openai_rate_limit_error(self, mock_openai_class):
        """Test handling of OpenAI rate limit error."""
        from openai import RateLimitError
        
        # Mock OpenAI client to raise rate limit error
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        # Create a mock response object with request attribute
        mock_response = MagicMock()
        mock_response.request = MagicMock()
        
        mock_client.chat.completions.create.side_effect = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body=None
        )
        
        # Replace the client's openai_client
        self.client.openai_client = mock_client
        
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(GPTRateLimitError) as context:
            self.client._make_api_call(messages)
        
        self.assertIn("Rate limit exceeded", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_api_call_openai_api_error(self, mock_openai_class):
        """Test handling of OpenAI API error."""
        from openai import APIError
        
        # Mock OpenAI client to raise API error
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIError(
            message="API Error occurred",
            request=None,
            body=None
        )
        
        # Replace the client's openai_client
        self.client.openai_client = mock_client
        
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(SummarizationError) as context:
            self.client._make_api_call(messages)
        
        self.assertIn("Failed to call OpenAI API", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_api_call_unexpected_error(self, mock_openai_class):
        """Test handling of unexpected errors."""
        # Mock OpenAI client to raise unexpected error
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = ConnectionError("Network error")
        
        # Replace the client's openai_client
        self.client.openai_client = mock_client
        
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(SummarizationError) as context:
            self.client._make_api_call(messages)
        
        self.assertIn("Unexpected error", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_api_call_empty_response_choices(self, mock_openai_class):
        """Test handling of empty response choices."""
        # Mock OpenAI client to return empty choices
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client.chat.completions.create.return_value = mock_response
        
        # Replace the client's openai_client
        self.client.openai_client = mock_client
        
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(SummarizationError) as context:
            self.client._make_api_call(messages)
        
        self.assertIn("Empty response from OpenAI API", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_api_call_empty_message_content(self, mock_openai_class):
        """Test handling of empty message content."""
        # Mock OpenAI client to return empty content
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_choice = MagicMock()
        mock_choice.message.content = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Replace the client's openai_client
        self.client.openai_client = mock_client
        
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(SummarizationError) as context:
            self.client._make_api_call(messages)
        
        self.assertIn("Empty response from OpenAI API", str(context.exception))
    
    def test_check_rate_limit_enforcement(self):
        """Test rate limit check and enforcement."""
        # Mock rate limiter to indicate limit exceeded
        with patch.object(self.client.rate_limiter, 'can_make_request', return_value=False):
            with patch.object(self.client.rate_limiter, 'wait_time', return_value=30.5):
                with self.assertRaises(GPTRateLimitError) as context:
                    self.client._check_rate_limit()
                
                self.assertIn("Rate limit exceeded", str(context.exception))
                self.assertIn("30.50 seconds", str(context.exception))
    
    def test_check_rate_limit_records_request(self):
        """Test rate limit check records request when allowed."""
        with patch.object(self.client.rate_limiter, 'can_make_request', return_value=True):
            with patch.object(self.client.rate_limiter, 'record_request') as mock_record:
                self.client._check_rate_limit()
                mock_record.assert_called_once()


class TestChecklistValidationEdgeCases(TestCase):
    """Test checklist validation edge cases."""
    
    def setUp(self):
        """Set up test client."""
        self.client = GPTClient(api_key="test-api-key")
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_non_list_response(self, mock_api_call):
        """Test checklist generation with non-list JSON response."""
        mock_api_call.return_value = '{"not": "a list"}'
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist("Test summary")
        
        self.assertIn("Checklist response must be a JSON array", str(context.exception))
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_empty_list_response(self, mock_api_call):
        """Test checklist generation with empty list response."""
        mock_api_call.return_value = '[]'
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist("Test summary")
        
        self.assertIn("Empty checklist generated", str(context.exception))
    
    def test_validate_checklist_item_empty_strings(self):
        """Test checklist item validation with empty strings."""
        invalid_items = [
            {"id": 1, "title": "", "description": "Test", "priority": "high", "category": "test"},
            {"id": 1, "title": "Test", "description": "", "priority": "high", "category": "test"},
            {"id": 1, "title": "Test", "description": "Test", "priority": "high", "category": ""},
            {"id": 1, "title": "   ", "description": "Test", "priority": "high", "category": "test"},
        ]
        
        for item in invalid_items:
            with self.assertRaises(ChecklistGenerationError):
                self.client._validate_checklist_item(item)
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_item_validation_error(self, mock_api_call):
        """Test checklist generation with invalid item structure."""
        invalid_checklist = [
            {"id": 1, "title": "Valid item", "description": "Test", "priority": "high", "category": "test"},
            {"id": "invalid", "title": "Invalid item", "description": "Test", "priority": "high", "category": "test"}
        ]
        
        mock_api_call.return_value = json.dumps(invalid_checklist)
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist("Test summary")
        
        self.assertIn("Invalid checklist item at index 1", str(context.exception))
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_rate_limit_passthrough(self, mock_api_call):
        """Test checklist generation passes through rate limit errors."""
        mock_api_call.side_effect = GPTRateLimitError("Rate limit exceeded")
        
        with self.assertRaises(GPTRateLimitError):
            self.client.generate_checklist("Test summary")
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_validation_error_passthrough(self, mock_api_call):
        """Test checklist generation passes through validation errors."""
        mock_api_call.side_effect = GPTValidationError("Validation failed")
        
        with self.assertRaises(GPTValidationError):
            self.client.generate_checklist("Test summary")
    
    @patch.object(GPTClient, '_make_api_call')
    def test_generate_checklist_unexpected_error_wrapped(self, mock_api_call):
        """Test checklist generation wraps unexpected errors."""
        mock_api_call.side_effect = RuntimeError("Unexpected error")
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist("Test summary")
        
        self.assertIn("Failed to generate checklist", str(context.exception))


class TestRateLimiterFunctionality(APITestCase):
    """Test rate limiter functionality comprehensively."""
    
    def test_rate_limiter_record_request(self):
        """Test recording requests updates internal state."""
        limiter = RateLimiter(max_requests=5, time_window=60)
        
        # Initially no requests
        self.assertEqual(len(limiter.requests), 0)
        
        # Record a request
        limiter.record_request()
        self.assertEqual(len(limiter.requests), 1)
        
        # Record multiple requests
        for _ in range(3):
            limiter.record_request()
        self.assertEqual(len(limiter.requests), 4)
    
    def test_rate_limiter_wait_time_no_requests(self):
        """Test wait time calculation with no requests."""
        limiter = RateLimiter(max_requests=5, time_window=60)
        
        # No requests should return 0 wait time
        self.assertEqual(limiter.wait_time(), 0.0)
    
    def test_rate_limiter_wait_time_with_requests(self):
        """Test wait time calculation with existing requests."""
        limiter = RateLimiter(max_requests=2, time_window=60)
        
        # Fill up the rate limit
        limiter.record_request()
        limiter.record_request()
        
        # Should calculate wait time based on oldest request
        wait_time = limiter.wait_time()
        self.assertGreater(wait_time, 0)
        self.assertLessEqual(wait_time, 60)
    
    def test_rate_limiter_request_cleanup(self):
        """Test old requests are cleaned up properly."""
        limiter = RateLimiter(max_requests=5, time_window=1)  # 1 second window
        
        # Record requests
        limiter.record_request()
        limiter.record_request()
        self.assertEqual(len(limiter.requests), 2)
        
        # Wait for requests to age out
        import time
        time.sleep(1.1)
        
        # Check if we can make request (should clean up old ones)
        can_make = limiter.can_make_request()
        self.assertTrue(can_make)
        self.assertEqual(len(limiter.requests), 0)  # Old requests cleaned up
    
    def test_rate_limiter_max_requests_enforcement(self):
        """Test rate limiter properly enforces max requests."""
        limiter = RateLimiter(max_requests=3, time_window=60)
        
        # Should allow requests up to limit
        for i in range(3):
            self.assertTrue(limiter.can_make_request())
            limiter.record_request()
        
        # Should block additional requests
        self.assertFalse(limiter.can_make_request())


class TestGPTClientAdvancedErrorHandling(APITestCase):
    """Test advanced error handling scenarios in GPT client."""
    
    def setUp(self):
        """Set up test client with mock API key."""
        self.api_key = "test-api-key"
        self.client = GPTClient(api_key=self.api_key)
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_api_call_timeout_error(self, mock_openai_class):
        """Test handling of API timeout errors."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = TimeoutError("Request timeout")
        
        self.client.openai_client = mock_client
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(SummarizationError) as context:
            self.client._make_api_call(messages)
        
        self.assertIn("Unexpected error", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_api_call_invalid_response_structure(self, mock_openai_class):
        """Test handling of invalid response structure."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock response with no message attribute
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message = None
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        self.client.openai_client = mock_client
        messages = [{"role": "user", "content": "test"}]
        
        with self.assertRaises(SummarizationError) as context:
            self.client._make_api_call(messages)
        
        self.assertIn("Unexpected error", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_checklist_generation_json_decode_error(self, mock_openai_class):
        """Test handling of invalid JSON in checklist generation."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "This is not valid JSON {invalid}"
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        self.client.openai_client = mock_client
        
        summary = "Test summary for checklist generation"
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist(summary)
        
        self.assertIn("Invalid JSON response", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_checklist_generation_empty_response(self, mock_openai_class):
        """Test handling of empty response in checklist generation."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock empty response
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        self.client.openai_client = mock_client
        
        summary = "Test summary for checklist generation"
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist(summary)
        
        self.assertIn("Empty response", str(context.exception))
    
    @patch('guideline_ingestion.jobs.gpt_client.OpenAI')
    def test_checklist_generation_validation_error_propagation(self, mock_openai_class):
        """Test that validation errors are properly propagated."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock response with invalid checklist structure
        invalid_checklist = [
            {"id": "invalid_id", "title": "Test"}  # Missing fields, invalid types
        ]
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(invalid_checklist)
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        self.client.openai_client = mock_client
        
        summary = "Test summary for checklist generation"
        
        with self.assertRaises(ChecklistGenerationError) as context:
            self.client.generate_checklist(summary)
        
        # Should propagate the validation error
        self.assertIn("invalid checklist item", str(context.exception).lower())
    
    def test_process_guidelines_error_propagation(self):
        """Test that process_guidelines properly propagates errors from sub-methods."""
        # Mock summarize_guidelines to raise an error
        with patch.object(self.client, 'summarize_guidelines') as mock_summarize:
            mock_summarize.side_effect = SummarizationError("Test summarization error")
            
            with self.assertRaises(SummarizationError) as context:
                self.client.process_guidelines("Test guidelines")
            
            self.assertIn("Test summarization error", str(context.exception))
        
        # Mock generate_checklist to raise an error
        with patch.object(self.client, 'summarize_guidelines') as mock_summarize, \
             patch.object(self.client, 'generate_checklist') as mock_checklist:
            
            mock_summarize.return_value = "Test summary"
            mock_checklist.side_effect = ChecklistGenerationError("Test checklist error")
            
            with self.assertRaises(ChecklistGenerationError) as context:
                self.client.process_guidelines("Test guidelines")
            
            self.assertIn("Test checklist error", str(context.exception))