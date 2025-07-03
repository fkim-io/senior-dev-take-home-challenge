"""
GPT client for OpenAI API integration (TASK-012 TDD Implementation).

This module provides a production-ready GPT client for processing guidelines
through a two-step chain: summarization → checklist generation.

Features:
- Rate limiting with configurable limits
- Comprehensive error handling and retry logic
- Response validation and parsing
- Structured logging for monitoring
- Two-step GPT chain processing
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from openai import OpenAI
from openai.types.chat import ChatCompletion

logger = logging.getLogger(__name__)


class GPTClientError(Exception):
    """Base exception for GPT client errors."""
    pass


class GPTValidationError(GPTClientError):
    """Exception for input validation errors."""
    pass


class GPTRateLimitError(GPTClientError):
    """Exception for rate limiting errors."""
    pass


class SummarizationError(GPTClientError):
    """Exception for summarization step errors."""
    pass


class ChecklistGenerationError(GPTClientError):
    """Exception for checklist generation step errors."""
    pass


class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, max_requests: int, time_window: int):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed in time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    def can_make_request(self) -> bool:
        """Check if a request can be made without exceeding rate limit."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.time_window)
        
        # Remove old requests
        self.requests = [req_time for req_time in self.requests if req_time > cutoff]
        
        return len(self.requests) < self.max_requests
    
    def record_request(self):
        """Record a new request."""
        self.requests.append(datetime.now())
    
    def wait_time(self) -> float:
        """Calculate how long to wait before next request."""
        if not self.requests:
            return 0.0
        
        oldest_request = min(self.requests)
        wait_until = oldest_request + timedelta(seconds=self.time_window)
        now = datetime.now()
        
        if wait_until > now:
            return (wait_until - now).total_seconds()
        
        return 0.0


class GPTClient:
    """
    OpenAI GPT client for guidelines processing.
    
    Provides a two-step processing chain:
    1. Summarize input guidelines
    2. Generate actionable checklist from summary
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        max_tokens: int = 2000,
        temperature: float = 0.1,
        rate_limit_requests: int = 60,
        rate_limit_window: int = 60
    ):
        """
        Initialize GPT client.
        
        Args:
            api_key: OpenAI API key
            model: GPT model to use
            max_tokens: Maximum tokens per response
            temperature: Sampling temperature (0.0-1.0)
            rate_limit_requests: Max requests per time window
            rate_limit_window: Rate limit time window in seconds
        """
        if not api_key or not api_key.strip():
            raise GPTClientError("OpenAI API key is required")
        
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Initialize OpenAI client
        self.openai_client = OpenAI(api_key=api_key)
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(rate_limit_requests, rate_limit_window)
        
        logger.info(f"GPT client initialized with model {model}")
    
    def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        if not self.rate_limiter.can_make_request():
            wait_time = self.rate_limiter.wait_time()
            logger.warning(f"Rate limit exceeded, would need to wait {wait_time:.2f}s")
            raise GPTRateLimitError(f"Rate limit exceeded. Try again in {wait_time:.2f} seconds")
        
        self.rate_limiter.record_request()
    
    def _make_api_call(self, messages: List[Dict[str, str]]) -> str:
        """
        Make OpenAI API call with error handling.
        
        Args:
            messages: List of messages for the conversation
            
        Returns:
            Response content as string
            
        Raises:
            GPTRateLimitError: If rate limit is exceeded
            SummarizationError: If API call fails
        """
        self._check_rate_limit()
        
        try:
            logger.debug(f"Making OpenAI API call with {len(messages)} messages")
            
            response: ChatCompletion = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            if not response.choices or not response.choices[0].message.content:
                raise SummarizationError("Empty response from OpenAI API")
            
            content = response.choices[0].message.content.strip()
            
            logger.debug(f"OpenAI API call successful, {len(content)} characters returned")
            return content
            
        except Exception as e:
            from openai import RateLimitError, APIError
            
            if isinstance(e, RateLimitError):
                logger.warning(f"OpenAI rate limit exceeded: {e}")
                raise GPTRateLimitError(f"Rate limit exceeded: {e}")
            elif isinstance(e, APIError):
                logger.error(f"OpenAI API error: {e}")
                raise SummarizationError(f"Failed to call OpenAI API: {e}")
            else:
                logger.error(f"Unexpected error calling OpenAI API: {e}")
                raise SummarizationError(f"Unexpected error: {e}")
    
    def _validate_guidelines_input(self, guidelines: str):
        """Validate guidelines input."""
        if not guidelines or not guidelines.strip():
            raise GPTValidationError("Guidelines cannot be empty")
        
        if len(guidelines) > 10000:
            raise GPTValidationError("Guidelines too long (max 10,000 characters)")
    
    def _validate_summary(self, summary: str):
        """Validate summary output."""
        if not summary or len(summary.strip()) < 10:
            raise SummarizationError("Empty response or summary too short")
        
        if len(summary) > 3000:
            raise SummarizationError("Summary too long")
    
    def _validate_checklist_item(self, item: Dict[str, Any]):
        """Validate individual checklist item structure."""
        required_fields = ['id', 'title', 'description', 'priority', 'category']
        
        for field in required_fields:
            if field not in item:
                raise ChecklistGenerationError(f"Missing required field: {field}")
        
        # Validate types
        if not isinstance(item['id'], int):
            raise ChecklistGenerationError("Checklist item 'id' must be an integer")
        
        if not isinstance(item['title'], str) or not item['title'].strip():
            raise ChecklistGenerationError("Checklist item 'title' must be a non-empty string")
        
        if not isinstance(item['description'], str) or not item['description'].strip():
            raise ChecklistGenerationError("Checklist item 'description' must be a non-empty string")
        
        if item['priority'] not in ['high', 'medium', 'low']:
            raise ChecklistGenerationError("Checklist item 'priority' must be 'high', 'medium', or 'low'")
        
        if not isinstance(item['category'], str) or not item['category'].strip():
            raise ChecklistGenerationError("Checklist item 'category' must be a non-empty string")
    
    def summarize_guidelines(self, guidelines: str) -> str:
        """
        Summarize input guidelines using GPT.
        
        Args:
            guidelines: Raw guidelines text to summarize
            
        Returns:
            Concise summary of the guidelines
            
        Raises:
            GPTValidationError: If input validation fails
            GPTRateLimitError: If rate limit is exceeded
            SummarizationError: If summarization fails
        """
        logger.info("Starting guidelines summarization")
        
        # Validate input
        self._validate_guidelines_input(guidelines)
        
        # Prepare messages
        system_prompt = """You are an expert technical writer specializing in creating concise, actionable summaries of technical guidelines and documentation.

Your task is to summarize the provided guidelines into a clear, well-structured summary that captures the key points and themes. The summary should:

1. Be concise but comprehensive (100-300 words)
2. Highlight the main categories and themes
3. Focus on actionable insights
4. Use clear, professional language
5. Maintain the technical accuracy of the original content

Do not include implementation details or code examples in the summary. Focus on the high-level concepts and principles."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": guidelines}
        ]
        
        try:
            summary = self._make_api_call(messages)
            self._validate_summary(summary)
            
            logger.info("Guidelines summarization completed successfully")
            return summary
            
        except (GPTRateLimitError, GPTValidationError):
            raise
        except Exception as e:
            logger.error(f"Failed to summarize guidelines: {e}")
            raise SummarizationError(f"Failed to summarize guidelines: {e}")
    
    def generate_checklist(self, summary: str) -> List[Dict[str, Any]]:
        """
        Generate actionable checklist from summary using GPT.
        
        Args:
            summary: Summary text to convert to checklist
            
        Returns:
            List of checklist items with structure:
            [
                {
                    "id": int,
                    "title": str,
                    "description": str,
                    "priority": "high"|"medium"|"low",
                    "category": str
                }
            ]
            
        Raises:
            GPTValidationError: If input validation fails
            GPTRateLimitError: If rate limit is exceeded
            ChecklistGenerationError: If checklist generation fails
        """
        logger.info("Starting checklist generation")
        
        # Validate input
        if not summary or not summary.strip():
            raise GPTValidationError("Summary cannot be empty")
        
        # Prepare messages
        system_prompt = """You are an expert project manager specializing in creating actionable checklists from technical documentation summaries.

Your task is to convert the provided summary into a structured, actionable checklist. Each checklist item should be:

1. Specific and actionable
2. Properly prioritized (high/medium/low)
3. Categorized by domain (e.g., security, performance, testing, etc.)
4. Clear and concise

You MUST respond with a valid JSON array containing checklist items. Each item must have this exact structure:
{
    "id": <integer>,
    "title": "<short, actionable title>",
    "description": "<detailed description of what needs to be done>",
    "priority": "<high|medium|low>",
    "category": "<category name>"
}

Respond ONLY with the JSON array, no additional text or formatting."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create a checklist from this summary:\n\n{summary}"}
        ]
        
        try:
            response = self._make_api_call(messages)
            
            # Parse JSON response
            try:
                checklist = json.loads(response)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from GPT: {e}")
                raise ChecklistGenerationError(f"Invalid JSON response from GPT: {e}")
            
            # Validate response structure
            if not isinstance(checklist, list):
                raise ChecklistGenerationError("Checklist response must be a JSON array")
            
            if not checklist:
                raise ChecklistGenerationError("Empty checklist generated")
            
            # Validate each item
            for i, item in enumerate(checklist):
                try:
                    self._validate_checklist_item(item)
                except ChecklistGenerationError as e:
                    raise ChecklistGenerationError(f"Invalid checklist item at index {i}: {e}")
            
            logger.info(f"Checklist generation completed successfully, {len(checklist)} items generated")
            return checklist
            
        except (GPTRateLimitError, GPTValidationError):
            raise
        except ChecklistGenerationError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate checklist: {e}")
            raise ChecklistGenerationError(f"Failed to generate checklist: {e}")
    
    def process_guidelines(self, guidelines: str) -> Dict[str, Any]:
        """
        Process guidelines through complete two-step GPT chain.
        
        Step 1: Summarize the input guidelines
        Step 2: Generate actionable checklist from summary
        
        Args:
            guidelines: Raw guidelines text to process
            
        Returns:
            Dictionary containing:
            {
                "summary": str,
                "checklist": List[Dict[str, Any]]
            }
            
        Raises:
            GPTValidationError: If input validation fails
            GPTRateLimitError: If rate limit is exceeded
            SummarizationError: If summarization step fails
            ChecklistGenerationError: If checklist generation step fails
        """
        logger.info("Starting complete guidelines processing chain")
        start_time = time.time()
        
        try:
            # Step 1: Summarize guidelines
            logger.info("Step 1: Summarizing guidelines")
            summary = self.summarize_guidelines(guidelines)
            
            # Step 2: Generate checklist from summary
            logger.info("Step 2: Generating checklist from summary")
            checklist = self.generate_checklist(summary)
            
            result = {
                "summary": summary,
                "checklist": checklist
            }
            
            processing_time = time.time() - start_time
            logger.info(f"Complete guidelines processing completed in {processing_time:.2f}s")
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Guidelines processing failed after {processing_time:.2f}s: {e}")
            raise