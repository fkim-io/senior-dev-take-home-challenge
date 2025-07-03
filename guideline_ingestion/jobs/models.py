"""
Job models for guideline ingestion API.

This module contains the core Job model and related components for tracking
async job processing through the GPT chain workflow.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from django.db import models
from django.utils import timezone


class JobStatus(models.TextChoices):
    """
    Job lifecycle states with clear transitions and business logic.
    
    State Transitions:
    PENDING → PROCESSING → COMPLETED
    PENDING → PROCESSING → FAILED
    PROCESSING → FAILED (with retry) → PROCESSING (if retries < max)
    """
    
    PENDING = 'PENDING', 'Pending'
    PROCESSING = 'PROCESSING', 'Processing'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'
    
    @classmethod
    def get_terminal_statuses(cls):
        """Return statuses that indicate job completion."""
        return [cls.COMPLETED, cls.FAILED]
    
    @classmethod
    def get_active_statuses(cls):
        """Return statuses that indicate job is still being processed."""
        return [cls.PENDING, cls.PROCESSING]


class Job(models.Model):
    """
    Core model for tracking guideline processing jobs through the async GPT chain.
    
    Lifecycle: PENDING → PROCESSING → COMPLETED/FAILED
    Performance: <200ms job creation, indexed lookups, concurrent-safe updates
    """
    
    # Primary Fields
    id = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(
        unique=True, 
        default=uuid.uuid4,
        db_index=True,
        help_text="Public UUID for client tracking, generated automatically"
    )
    
    # Status Management
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
        db_index=True,
        help_text="Current job processing status"
    )
    
    # Input Data Storage
    input_data = models.JSONField(
        help_text="Original guidelines and metadata submitted by client"
    )
    
    # Result Storage (PostgreSQL JSONB)
    result = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        help_text="GPT chain outputs: summary and checklist"
    )
    
    # Error Handling
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Detailed error message if job fails"
    )
    
    # Metadata & Tracking
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Job submission timestamp"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last status update timestamp"
    )
    
    # Processing Metadata
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When worker began processing"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When job finished (success or failure)"
    )
    
    retry_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of retry attempts"
    )
    
    class Meta:
        db_table = 'jobs'
        ordering = ['-created_at']
        
        # Performance Indexes
        indexes = [
            # Primary lookup index for API queries
            models.Index(fields=['event_id'], name='jobs_event_id_idx'),
            
            # Status-based queries for monitoring
            models.Index(fields=['status'], name='jobs_status_idx'),
            
            # Time-based queries and sorting
            models.Index(fields=['created_at'], name='jobs_created_at_idx'),
            models.Index(fields=['updated_at'], name='jobs_updated_at_idx'),
            
            # Composite index for status + time queries
            models.Index(
                fields=['status', 'created_at'], 
                name='jobs_status_created_idx'
            ),
            
            # Failed job analysis
            models.Index(
                fields=['status', 'retry_count'],
                name='jobs_status_retry_idx',
                condition=models.Q(status__in=['FAILED', 'PROCESSING'])
            ),
        ]
        
        # Database constraints
        constraints = [
            models.CheckConstraint(
                condition=models.Q(retry_count__gte=0),
                name='jobs_retry_count_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(
                    models.Q(status='PENDING', started_at__isnull=True) |
                    models.Q(status='PROCESSING', started_at__isnull=False) |
                    models.Q(status__in=['COMPLETED', 'FAILED'])
                ),
                name='jobs_status_started_at_consistency'
            ),
        ]

    def __str__(self):
        return f"Job {self.event_id} ({self.status})"
    
    @property
    def is_terminal(self) -> bool:
        """Check if job has reached a terminal state."""
        return self.status in JobStatus.get_terminal_statuses()
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate job processing duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    def mark_as_processing(self) -> None:
        """Mark job as processing and set started_at timestamp."""
        self.status = JobStatus.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
    
    def mark_as_completed(self, result_data: Dict) -> None:
        """Mark job as completed with result data."""
        self.status = JobStatus.COMPLETED
        self.result = result_data
        self.completed_at = timezone.now()
        self.error_message = None
        self.save(update_fields=['status', 'result', 'completed_at', 'error_message', 'updated_at'])
    
    def mark_as_failed(self, error_message: str) -> None:
        """Mark job as failed with error message."""
        self.status = JobStatus.FAILED
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
    
    def increment_retry_count(self) -> None:
        """Increment retry count and save."""
        self.retry_count += 1
        self.save(update_fields=['retry_count', 'updated_at'])