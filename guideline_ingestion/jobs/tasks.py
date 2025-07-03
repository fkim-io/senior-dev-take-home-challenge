"""
Celery tasks for job processing.

This module contains async tasks for processing guideline jobs through
the GPT chain with comprehensive error handling and retry logic.
"""

import logging
import time
from typing import Dict, Any

from celery import shared_task
from celery.exceptions import Retry
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from guideline_ingestion.jobs.models import Job, JobStatus
from guideline_ingestion.jobs.gpt_client import (
    GPTClient,
    GPTClientError,
    GPTRateLimitError,
    GPTValidationError,
    SummarizationError,
    ChecklistGenerationError,
)

logger = logging.getLogger(__name__)


class JobProcessingError(Exception):
    """Base exception for job processing errors."""
    pass


class TemporaryProcessingError(JobProcessingError):
    """Temporary error that should trigger a retry."""
    pass


class PermanentProcessingError(JobProcessingError):
    """Permanent error that should not retry."""
    pass


def process_guidelines_with_gpt(guidelines: str) -> Dict[str, Any]:
    """
    Process guidelines through GPT chain (TASK-012 Implementation).
    
    Implements a two-step GPT processing chain:
    1. Summarize input guidelines using GPT-4
    2. Generate actionable checklist from summary
    
    Args:
        guidelines: Raw guidelines text to process
        
    Returns:
        Dictionary containing:
        {
            "summary": str,
            "checklist": List[Dict[str, Any]]
        }
        
    Raises:
        PermanentProcessingError: For validation errors or permanent failures
        TemporaryProcessingError: For rate limiting or temporary API errors
    """
    logger.info("Starting GPT guidelines processing")
    
    if not guidelines or not guidelines.strip():
        raise PermanentProcessingError("Guidelines cannot be empty")
    
    try:
        # Initialize GPT client
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise PermanentProcessingError("OpenAI API key not configured")
        
        client = GPTClient(
            api_key=api_key,
            model=getattr(settings, 'OPENAI_MODEL', 'gpt-4'),
            max_tokens=getattr(settings, 'OPENAI_MAX_TOKENS', 2000),
            temperature=getattr(settings, 'OPENAI_TEMPERATURE', 0.1),
            rate_limit_requests=getattr(settings, 'OPENAI_RATE_LIMIT_REQUESTS', 60),
            rate_limit_window=getattr(settings, 'OPENAI_RATE_LIMIT_WINDOW', 60)
        )
        
        # Process guidelines through two-step chain
        result = client.process_guidelines(guidelines)
        
        logger.info("GPT guidelines processing completed successfully")
        return result
        
    except GPTValidationError as e:
        logger.error(f"GPT validation error: {e}")
        raise PermanentProcessingError(f"Invalid input: {e}")
        
    except GPTRateLimitError as e:
        logger.warning(f"GPT rate limit exceeded: {e}")
        raise TemporaryProcessingError(f"Rate limit exceeded: {e}")
        
    except (SummarizationError, ChecklistGenerationError) as e:
        logger.error(f"GPT processing error: {e}")
        
        # Check if this is a temporary error that should retry
        error_message = str(e).lower()
        if any(indicator in error_message for indicator in [
            'rate limit', 'timeout', 'connection', 'network', 'server error',
            'service unavailable', 'temporary', '5xx'
        ]):
            raise TemporaryProcessingError(f"Temporary GPT error: {e}")
        else:
            raise PermanentProcessingError(f"GPT processing failed: {e}")
            
    except GPTClientError as e:
        logger.error(f"GPT client error: {e}")
        raise PermanentProcessingError(f"GPT client error: {e}")
        
    except Exception as e:
        logger.exception(f"Unexpected error in GPT processing: {e}")
        raise PermanentProcessingError(f"Unexpected GPT error: {e}")


@shared_task(bind=True, autoretry_for=(TemporaryProcessingError,), retry_kwargs={'max_retries': 3})
def process_guideline_job(self, job_id: int, guidelines: str):
    """
    Process a guideline job through the GPT chain.
    
    Args:
        job_id: ID of the job to process
        guidelines: Guidelines text to process
        
    Returns:
        Dict containing processing results
        
    Raises:
        PermanentProcessingError: For errors that should not retry
        TemporaryProcessingError: For errors that should retry
    """
    logger.info(f"Starting processing for job {job_id}")
    
    try:
        # Validate input
        if not guidelines or not guidelines.strip():
            with transaction.atomic():
                try:
                    job = Job.objects.select_for_update().get(id=job_id)
                    job.mark_as_failed("Guidelines cannot be empty")
                except Job.DoesNotExist:
                    logger.error(f"Job {job_id} not found during validation")
            raise PermanentProcessingError("Guidelines cannot be empty")
        
        # Get job and validate state
        with transaction.atomic():
            try:
                job = Job.objects.select_for_update().get(id=job_id)
            except Job.DoesNotExist:
                logger.error(f"Job {job_id} not found")
                raise PermanentProcessingError(f"Job {job_id} not found")
            
            # Check if job is already being processed
            if job.status == JobStatus.PROCESSING:
                logger.warning(f"Job {job_id} is already being processed")
                raise PermanentProcessingError(f"Job {job_id} is already being processed")
            
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                logger.warning(f"Job {job_id} is already finished with status {job.status}")
                raise PermanentProcessingError(f"Job {job_id} is already finished with status {job.status}")
            
            # Mark job as processing
            job.mark_as_processing()
            logger.info(f"Marked job {job_id} as processing")
        
        try:
            # Process guidelines through GPT chain
            result = process_guidelines_with_gpt(guidelines)
            
            # Mark job as completed with results
            with transaction.atomic():
                job.refresh_from_db()
                job.mark_as_completed(result)
                
            logger.info(f"Successfully completed job {job_id}")
            return result
            
        except Exception as e:
            error_message = str(e)
            
            # Categorize error for retry logic
            if _should_retry_error(error_message):
                # Increment retry count
                with transaction.atomic():
                    job.refresh_from_db()
                    job.increment_retry_count()
                
                # Calculate backoff delay
                retry_count = job.retry_count
                countdown = _calculate_retry_delay(retry_count)
                
                logger.warning(f"Temporary error for job {job_id}, retry {retry_count}: {error_message}")
                
                if retry_count >= 3:
                    # Max retries exceeded, mark as failed
                    with transaction.atomic():
                        job.refresh_from_db()
                        job.mark_as_failed(f"Max retries exceeded. Last error: {error_message}")
                    
                    logger.error(f"Max retries exceeded for job {job_id}")
                    raise PermanentProcessingError(f"Max retries exceeded: {error_message}")
                
                # Retry with exponential backoff
                raise self.retry(countdown=countdown, exc=e)
            else:
                # Permanent error, mark job as failed
                with transaction.atomic():
                    job.refresh_from_db()
                    job.mark_as_failed(error_message)
                
                logger.error(f"Permanent error for job {job_id}: {error_message}")
                raise PermanentProcessingError(error_message)
    
    except (PermanentProcessingError, Retry):
        # Re-raise these exceptions as-is
        raise
    except Exception as e:
        # Unexpected error - log and mark job as failed
        error_message = f"Unexpected error: {str(e)}"
        logger.exception(f"Unexpected error processing job {job_id}")
        
        try:
            with transaction.atomic():
                job = Job.objects.get(id=job_id)
                job.mark_as_failed(error_message)
        except:
            # Even job update failed - log but don't crash
            logger.exception(f"Failed to update job {job_id} status after error")
        
        raise PermanentProcessingError(error_message)


def _should_retry_error(error_message: str) -> bool:
    """
    Determine if an error should trigger a retry.
    
    Args:
        error_message: The error message to analyze
        
    Returns:
        True if the error should trigger a retry, False otherwise
    """
    retry_indicators = [
        'rate limit',
        'timeout',
        'connection',
        'network',
        'server error',
        'service unavailable',
        'temporary',
        '5xx',
        'retry',
    ]
    
    no_retry_indicators = [
        'invalid api key',
        'authentication',
        'authorization',
        'permission denied',
        'not found',
        'bad request',
        'invalid input',
        'malformed',
        '4xx',
    ]
    
    error_lower = error_message.lower()
    
    # Check for no-retry indicators first
    for indicator in no_retry_indicators:
        if indicator in error_lower:
            return False
    
    # Check for retry indicators
    for indicator in retry_indicators:
        if indicator in error_lower:
            return True
    
    # Default to retry for unknown errors (conservative approach)
    return True


def _calculate_retry_delay(retry_count: int) -> int:
    """
    Calculate retry delay with exponential backoff.
    
    Args:
        retry_count: Current retry attempt number
        
    Returns:
        Delay in seconds before next retry
    """
    # Exponential backoff: 60, 120, 240 seconds
    base_delay = 60
    max_delay = 300  # 5 minutes max
    
    delay = min(base_delay * (2 ** retry_count), max_delay)
    return delay


@shared_task
def cleanup_old_jobs(retention_days: int = 30):
    """
    Cleanup old completed/failed jobs to prevent database bloat.
    
    Args:
        retention_days: Number of days to retain completed/failed jobs (default: 30)
    
    Returns:
        str: Summary of cleanup operation
    """
    from datetime import timedelta
    from django.utils import timezone
    from guideline_ingestion.jobs.models import Job, JobStatus
    
    cutoff_date = timezone.now() - timedelta(days=retention_days)
    
    # Only cleanup completed and failed jobs, keep pending/processing
    old_jobs = Job.objects.filter(
        status__in=[JobStatus.COMPLETED, JobStatus.FAILED],
        completed_at__lt=cutoff_date
    )
    
    deleted_count = old_jobs.count()
    if deleted_count > 0:
        old_jobs.delete()
        logger.info(f"Cleanup completed: removed {deleted_count} old jobs older than {retention_days} days")
    else:
        logger.info(f"Cleanup completed: no old jobs found older than {retention_days} days")
    
    return f"Cleanup completed: {deleted_count} jobs removed"


@shared_task
def monitor_job_health():
    """
    Monitor job processing health and send alerts if needed.
    
    Checks for stuck jobs, failed job rates, and processing performance.
    Provides metrics and alerts for job processing health monitoring.
    
    Returns:
        str: Summary of health monitoring results
    """
    from datetime import timedelta
    from django.utils import timezone
    from guideline_ingestion.jobs.models import Job, JobStatus
    
    now = timezone.now()
    health_report = []
    
    # Check for stuck jobs (processing for >30 minutes)
    stuck_threshold = now - timedelta(minutes=30)
    stuck_jobs = Job.objects.filter(
        status=JobStatus.PROCESSING,
        started_at__lt=stuck_threshold
    )
    
    stuck_count = stuck_jobs.count()
    if stuck_count > 0:
        logger.warning(f"Found {stuck_count} stuck jobs processing for >30 minutes")
        health_report.append(f"ALERT: {stuck_count} stuck jobs detected")
        
        # Log details of stuck jobs
        for job in stuck_jobs[:5]:  # Log first 5 stuck jobs
            duration = now - job.started_at
            logger.warning(f"Stuck job {job.event_id}: processing for {duration.total_seconds():.0f}s")
    else:
        health_report.append("No stuck jobs detected")
    
    # Check failed job rate in last hour
    one_hour_ago = now - timedelta(hours=1)
    recent_jobs = Job.objects.filter(created_at__gte=one_hour_ago)
    failed_jobs = recent_jobs.filter(status=JobStatus.FAILED)
    
    total_recent = recent_jobs.count()
    failed_recent = failed_jobs.count()
    
    if total_recent > 0:
        failure_rate = (failed_recent / total_recent) * 100
        if failure_rate > 20:  # Alert if >20% failure rate
            logger.warning(f"High failure rate: {failure_rate:.1f}% ({failed_recent}/{total_recent}) in last hour")
            health_report.append(f"ALERT: High failure rate {failure_rate:.1f}%")
        else:
            health_report.append(f"Failure rate: {failure_rate:.1f}% ({failed_recent}/{total_recent})")
    else:
        health_report.append("No recent jobs to analyze")
    
    # Check queue backlog
    pending_jobs = Job.objects.filter(status=JobStatus.PENDING).count()
    if pending_jobs > 50:  # Alert if >50 jobs queued
        logger.warning(f"Large queue backlog: {pending_jobs} pending jobs")
        health_report.append(f"ALERT: Large queue backlog ({pending_jobs} pending)")
    else:
        health_report.append(f"Queue backlog: {pending_jobs} pending jobs")
    
    # Check processing times for completed jobs in last hour
    completed_jobs = Job.objects.filter(
        status=JobStatus.COMPLETED,
        completed_at__gte=one_hour_ago,
        started_at__isnull=False
    )
    
    if completed_jobs.exists():
        processing_times = []
        for job in completed_jobs:
            duration = job.completed_at - job.started_at
            processing_times.append(duration.total_seconds())
        
        if processing_times:
            avg_time = sum(processing_times) / len(processing_times)
            max_time = max(processing_times)
            
            if avg_time > 120:  # Alert if average >2 minutes
                logger.warning(f"Slow processing: avg {avg_time:.1f}s, max {max_time:.1f}s")
                health_report.append(f"ALERT: Slow processing (avg {avg_time:.1f}s)")
            else:
                health_report.append(f"Processing times: avg {avg_time:.1f}s, max {max_time:.1f}s")
    else:
        health_report.append("No completed jobs to analyze processing times")
    
    # Log summary
    summary = "; ".join(health_report)
    logger.info(f"Job health monitoring completed: {summary}")
    
    return f"Health monitoring completed: {summary}"