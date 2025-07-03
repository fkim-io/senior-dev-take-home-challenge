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

from guideline_ingestion.jobs.models import Job, JobStatus


class JobCreateSerializer(serializers.Serializer):
    """Serializer for job creation requests with comprehensive validation."""
    
    guidelines = serializers.CharField(
        min_length=10,
        max_length=10000,
        help_text="Guidelines text to process (10-10000 characters)"
    )
    
    callback_url = serializers.URLField(
        required=False,
        allow_blank=True,
        help_text="HTTPS callback URL for job completion notification"
    )
    
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high'],
        default='normal',
        required=False,
        help_text="Job processing priority"
    )
    
    metadata = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Optional metadata key-value pairs"
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
    """Serializer for job status retrieval with status-specific fields."""
    
    event_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    
    # Conditional fields based on status
    estimated_completion = serializers.SerializerMethodField()
    queue_position = serializers.SerializerMethodField()
    started_at = serializers.DateTimeField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True)
    processing_time_seconds = serializers.SerializerMethodField()
    current_step = serializers.SerializerMethodField()
    result = serializers.JSONField(read_only=True)
    error_message = serializers.CharField(read_only=True)
    retry_count = serializers.IntegerField(read_only=True)
    metadata = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            'event_id', 'status', 'created_at', 'updated_at',
            'estimated_completion', 'queue_position', 'started_at',
            'completed_at', 'processing_time_seconds', 'current_step',
            'result', 'error_message', 'retry_count', 'metadata'
        ]
    
    def get_estimated_completion(self, obj: Job) -> str:
        """Calculate estimated completion time."""
        if obj.status in [JobStatus.PENDING, JobStatus.PROCESSING]:
            # Estimate 90 seconds processing time
            estimated_time = obj.created_at + timedelta(seconds=90)
            return estimated_time.isoformat()
        return None
    
    def get_queue_position(self, obj: Job) -> int:
        """Calculate queue position for pending jobs."""
        if obj.status == JobStatus.PENDING:
            # Count pending jobs created before this one
            position = Job.objects.filter(
                status=JobStatus.PENDING,
                created_at__lt=obj.created_at
            ).count() + 1
            return position
        return None
    
    def get_processing_time_seconds(self, obj: Job) -> float:
        """Calculate processing time for completed/failed jobs."""
        if obj.started_at and obj.completed_at:
            duration = obj.completed_at - obj.started_at
            return round(duration.total_seconds(), 2)
        return None
    
    def get_current_step(self, obj: Job) -> str:
        """Get current processing step for processing jobs."""
        if obj.status == JobStatus.PROCESSING:
            # In production, this would come from actual processing state
            return "summarization"
        return None
    
    def get_metadata(self, obj: Job) -> Dict[str, Any]:
        """Get processing metadata for completed jobs."""
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
    """Serializer for job listing with minimal fields."""
    
    event_id = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = Job
        fields = ['event_id', 'status', 'created_at', 'updated_at']