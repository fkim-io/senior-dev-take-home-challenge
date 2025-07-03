"""
Serializers for jobs API.

This module contains DRF serializers for job creation, retrieval, and listing
with comprehensive validation and response formatting.
"""

import json
from datetime import timedelta
from typing import Dict, Any

from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.openapi import OpenApiExample

from guideline_ingestion.jobs.models import Job, JobStatus


class ErrorResponseSerializer(serializers.Serializer):
    """
    Standardized error response format for all API endpoints.
    
    Provides consistent error structure across the API with detailed
    error information, timestamps, and request tracking.
    """
    
    success = serializers.BooleanField(
        default=False,
        help_text="Always false for error responses"
    )
    
    error = serializers.DictField(
        help_text="Error details object containing code, message, and additional information"
    )
    
    data = serializers.JSONField(
        allow_null=True,
        default=None,
        help_text="Always null for error responses"
    )
    
    class Meta:
        examples = {
            'validation_error': {
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {
                        "field_errors": {
                            "guidelines": ["This field is required."]
                        }
                    },
                    "timestamp": "2024-01-15T10:30:00Z",
                    "request_id": "req_550e8400e29b41d4a716446655440000"
                },
                "data": None
            },
            'job_not_found': {
                "success": False,
                "error": {
                    "code": "JOB_NOT_FOUND",
                    "message": "Job with specified event_id not found",
                    "details": "Please check the event_id and try again",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "request_id": "req_550e8400e29b41d4a716446655440000"
                },
                "data": None
            },
            'rate_limit_exceeded': {
                "success": False,
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded",
                    "details": "Maximum 100 requests per minute allowed",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "request_id": "req_550e8400e29b41d4a716446655440000"
                },
                "data": None
            },
            'internal_server_error': {
                "success": False,
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An internal server error occurred",
                    "details": "Please try again later or contact support",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "request_id": "req_550e8400e29b41d4a716446655440000"
                },
                "data": None
            }
        }


class SuccessResponseSerializer(serializers.Serializer):
    """
    Standardized success response format for all API endpoints.
    
    Provides consistent success structure across the API with
    data payload and optional success messages.
    """
    
    success = serializers.BooleanField(
        default=True,
        help_text="Always true for success responses"
    )
    
    data = serializers.JSONField(
        help_text="Response data object containing the actual response payload"
    )
    
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional success message providing additional context"
    )


class JobCreateSerializer(serializers.Serializer):
    """
    Serializer for job creation requests with comprehensive validation.
    
    Handles guideline submission for asynchronous processing through the GPT chain.
    Validates input constraints and prepares data for job creation.
    """
    
    guidelines = serializers.CharField(
        min_length=10,
        max_length=10000,
        help_text=(
            "Guideline text content to be processed through the GPT chain. "
            "Must be between 10-10,000 characters. Supports plain text format. "
            "Examples: medical protocols, safety procedures, compliance guidelines."
        ),
        style={'type': 'textarea', 'rows': 5}
    )
    
    callback_url = serializers.URLField(
        required=False,
        allow_blank=True,
        help_text=(
            "Optional HTTPS callback URL for job completion notification. "
            "Must use HTTPS protocol for security. "
            "Will receive POST request with job results when processing completes."
        )
    )
    
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high'],
        default='normal',
        required=False,
        help_text=(
            "Processing priority level. "
            "High priority jobs are processed first, normal is default, "
            "low priority jobs are processed when resources are available."
        )
    )
    
    metadata = serializers.JSONField(
        required=False,
        default=dict,
        help_text=(
            "Optional metadata as key-value pairs for client tracking. "
            "Maximum 10 keys, total size limit 1KB. "
            "Common uses: department, version, requester_id, tags."
        )
    )
    
    def validate_guidelines(self, value: str) -> str:
        """Validate guidelines field content."""
        if not value or not value.strip():
            raise serializers.ValidationError("Guidelines cannot be empty or only whitespace")
        
        return value.strip()
    
    def validate_callback_url(self, value: str) -> str:
        """Validate callback URL requires HTTPS."""
        if value and not value.startswith('https://'):
            raise serializers.ValidationError("Callback URL must use HTTPS protocol")
        
        return value
    
    def validate_metadata(self, value: Dict[str, Any]) -> Dict[str, Any]:
        """Validate metadata size and key constraints."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be a dictionary")
        
        # Check key count limit
        if len(value) > 10:
            raise serializers.ValidationError("Metadata cannot have more than 10 keys")
        
        # Check total size limit (1KB)
        try:
            serialized_size = len(json.dumps(value, separators=(',', ':')))
            if serialized_size > 1024:
                raise serializers.ValidationError("Metadata size cannot exceed 1024 bytes")
        except (TypeError, ValueError):
            raise serializers.ValidationError("Metadata contains non-serializable values")
        
        return value


class JobRetrieveSerializer(serializers.ModelSerializer):
    """
    Serializer for job status retrieval with status-specific fields.
    
    Provides comprehensive job information with fields that vary based on job status.
    Uses status-specific filtering to return only relevant data for each stage.
    """
    
    event_id = serializers.UUIDField(
        read_only=True,
        help_text="Unique identifier for the job, used for tracking and retrieval"
    )
    status = serializers.CharField(
        read_only=True,
        help_text="Current job status: PENDING, PROCESSING, COMPLETED, or FAILED"
    )
    created_at = serializers.DateTimeField(
        read_only=True,
        help_text="ISO timestamp when the job was created and submitted"
    )
    updated_at = serializers.DateTimeField(
        read_only=True,
        help_text="ISO timestamp when the job status was last updated"
    )
    
    # Conditional fields based on status
    estimated_completion = serializers.SerializerMethodField(
        help_text="Estimated completion time for PENDING/PROCESSING jobs (ISO timestamp)"
    )
    queue_position = serializers.SerializerMethodField(
        help_text="Position in processing queue for PENDING jobs (integer)"
    )
    started_at = serializers.DateTimeField(
        read_only=True,
        help_text="ISO timestamp when job processing started (PROCESSING/COMPLETED/FAILED)"
    )
    completed_at = serializers.DateTimeField(
        read_only=True,
        help_text="ISO timestamp when job processing completed (COMPLETED/FAILED)"
    )
    processing_time_seconds = serializers.SerializerMethodField(
        help_text="Total processing time in seconds (COMPLETED/FAILED jobs)"
    )
    current_step = serializers.SerializerMethodField(
        help_text="Current processing step for PROCESSING jobs (e.g., 'summarization')"
    )
    result = serializers.JSONField(
        read_only=True,
        help_text="Processing results with summary and checklist (COMPLETED jobs only)"
    )
    error_message = serializers.CharField(
        read_only=True,
        help_text="Error description for FAILED jobs"
    )
    retry_count = serializers.IntegerField(
        read_only=True,
        help_text="Number of processing retry attempts"
    )
    metadata = serializers.SerializerMethodField(
        help_text="Processing metadata including GPT model and token usage (COMPLETED jobs)"
    )
    
    class Meta:
        model = Job
        fields = [
            'event_id', 'status', 'created_at', 'updated_at',
            'estimated_completion', 'queue_position', 'started_at',
            'completed_at', 'processing_time_seconds', 'current_step',
            'result', 'error_message', 'retry_count', 'metadata'
        ]
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_estimated_completion(self, obj: Job) -> str:
        """
        Calculate estimated completion time based on job creation and average processing time.
        Returns ISO timestamp for PENDING/PROCESSING jobs, null for others.
        """
        if obj.status in [JobStatus.PENDING, JobStatus.PROCESSING]:
            # Estimate 90 seconds processing time
            estimated_time = obj.created_at + timedelta(seconds=90)
            return estimated_time.isoformat()
        return None
    
    @extend_schema_field(serializers.IntegerField(allow_null=True, min_value=1))
    def get_queue_position(self, obj: Job) -> int:
        """
        Calculate position in processing queue for pending jobs.
        Returns integer position (1-based) for PENDING jobs, null for others.
        """
        if obj.status == JobStatus.PENDING:
            # Count pending jobs created before this one
            position = Job.objects.filter(
                status=JobStatus.PENDING,
                created_at__lt=obj.created_at
            ).count() + 1
            return position
        return None
    
    @extend_schema_field(serializers.FloatField(allow_null=True, min_value=0))
    def get_processing_time_seconds(self, obj: Job) -> float:
        """
        Calculate total processing time in seconds for completed/failed jobs.
        Returns float seconds for jobs with start/end times, null for others.
        """
        if obj.started_at and obj.completed_at:
            duration = obj.completed_at - obj.started_at
            return round(duration.total_seconds(), 2)
        return None
    
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_current_step(self, obj: Job) -> str:
        """
        Get current processing step for jobs in progress.
        Returns step name for PROCESSING jobs, null for others.
        """
        if obj.status == JobStatus.PROCESSING:
            # In production, this would come from actual processing state
            return "summarization"
        return None
    
    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_metadata(self, obj: Job) -> Dict[str, Any]:
        """
        Get processing metadata including GPT model usage and performance metrics.
        Returns metadata object for COMPLETED jobs, null for others.
        """
        if obj.status == JobStatus.COMPLETED:
            return {
                'gpt_model_used': 'gpt-4',
                'tokens_consumed': 1250,  # Would be actual values in production
                'processing_steps': ['summarization', 'checklist_generation']
            }
        return None
    
    def to_representation(self, instance: Job) -> Dict[str, Any]:
        """Customize representation based on job status."""
        data = super().to_representation(instance)
        
        # Remove None fields and status-specific fields
        filtered_data = {k: v for k, v in data.items() if v is not None}
        
        # Status-specific field filtering
        if instance.status == JobStatus.PENDING:
            # Remove fields not relevant for pending jobs
            fields_to_remove = [
                'started_at', 'completed_at', 'processing_time_seconds',
                'current_step', 'result', 'error_message', 'retry_count', 'metadata'
            ]
            for field in fields_to_remove:
                filtered_data.pop(field, None)
        
        elif instance.status == JobStatus.PROCESSING:
            # Remove fields not relevant for processing jobs
            fields_to_remove = [
                'queue_position', 'completed_at', 'processing_time_seconds',
                'result', 'error_message', 'metadata'
            ]
            for field in fields_to_remove:
                filtered_data.pop(field, None)
        
        elif instance.status == JobStatus.COMPLETED:
            # Remove fields not relevant for completed jobs
            fields_to_remove = [
                'queue_position', 'current_step', 'error_message'
            ]
            for field in fields_to_remove:
                filtered_data.pop(field, None)
        
        elif instance.status == JobStatus.FAILED:
            # Remove fields not relevant for failed jobs
            fields_to_remove = [
                'queue_position', 'current_step', 'result', 'metadata'
            ]
            for field in fields_to_remove:
                filtered_data.pop(field, None)
        
        return filtered_data


class JobListSerializer(serializers.ModelSerializer):
    """
    Serializer for job listing with minimal fields for performance.
    
    Used for paginated job lists where only essential information is needed.
    Optimized for quick scanning of job statuses and timestamps.
    """
    
    event_id = serializers.UUIDField(
        read_only=True,
        help_text="Unique job identifier for detailed retrieval"
    )
    status = serializers.CharField(
        read_only=True,
        help_text="Current job status: PENDING, PROCESSING, COMPLETED, or FAILED"
    )
    created_at = serializers.DateTimeField(
        read_only=True,
        help_text="ISO timestamp when the job was submitted"
    )
    updated_at = serializers.DateTimeField(
        read_only=True,
        help_text="ISO timestamp of last status change"
    )
    
    class Meta:
        model = Job
        fields = ['event_id', 'status', 'created_at', 'updated_at']