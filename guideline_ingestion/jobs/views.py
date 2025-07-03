"""
Views for jobs API endpoints.

This module contains DRF views for job creation and retrieval with
performance optimization and comprehensive error handling.
"""

import uuid
import logging
from datetime import timedelta
from typing import Dict, Any

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, ParseError

from guideline_ingestion.jobs.models import Job, JobStatus
from guideline_ingestion.jobs.serializers import (
    JobCreateSerializer,
    JobRetrieveSerializer
)

logger = logging.getLogger(__name__)


class JobCreateView(APIView):
    """
    Create new job for guideline processing.
    
    POST /jobs/
    Performance requirement: <200ms response time
    """
    
    def post(self, request) -> Response:
        """Create new job and queue for async processing."""
        try:
            # 1. Validate request data (<10ms)
            serializer = JobCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return self._validation_error_response(serializer.errors, request)
            
            # 2. Create job record in database (<50ms)
            job = self._create_job(serializer.validated_data)
            
            # 3. Queue async processing task (<20ms)
            self._queue_processing_task(job, serializer.validated_data.get('guidelines'))
            
            # 4. Return success response (<10ms)
            return self._success_response(job)
            
        except Exception as e:
            logger.exception(f"Unexpected error in job creation: {str(e)}")
            return self._internal_error_response(request)
    
    def _create_job(self, validated_data: Dict[str, Any]) -> Job:
        """Create job record with validated data."""
        # Prepare input data for storage
        input_data = {
            'guidelines': validated_data['guidelines'],
            'priority': validated_data.get('priority', 'normal'),
        }
        
        # Add optional fields if present
        if 'callback_url' in validated_data and validated_data['callback_url']:
            input_data['callback_url'] = validated_data['callback_url']
        
        if 'metadata' in validated_data and validated_data['metadata']:
            input_data['metadata'] = validated_data['metadata']
        
        # Create job with default PENDING status
        job = Job.objects.create(
            status=JobStatus.PENDING,
            input_data=input_data
        )
        
        return job
    
    def _queue_processing_task(self, job: Job, guidelines: str) -> None:
        """Queue async processing task via Celery."""
        try:
            from guideline_ingestion.jobs.tasks import process_guideline_job
            process_guideline_job.delay(job.id, guidelines)
            
            logger.info(f"Queued processing task for job {job.event_id}")
            
        except ImportError:
            # Graceful fallback if Celery tasks not available yet
            logger.warning(f"Celery task not available for job {job.event_id}")
        except Exception as e:
            logger.error(f"Failed to queue task for job {job.event_id}: {str(e)}")
            # Don't fail the request if task queueing fails
    
    def _success_response(self, job: Job) -> Response:
        """Generate standardized success response."""
        response_data = {
            'success': True,
            'data': {
                'event_id': str(job.event_id),
                'status': job.status,
                'created_at': job.created_at.isoformat(),
                'estimated_completion': (job.created_at + timedelta(seconds=90)).isoformat()
            },
            'message': 'Job submitted successfully'
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
    
    def _validation_error_response(self, errors: Dict, request) -> Response:
        """Generate standardized validation error response."""
        response_data = {
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': 'Request validation failed',
                'details': {'field_errors': errors},
                'timestamp': timezone.now().isoformat(),
                'request_id': request.META.get('REQUEST_ID', 'unknown')
            },
            'data': None
        }
        
        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
    
    def _internal_error_response(self, request) -> Response:
        """Generate standardized internal error response."""
        response_data = {
            'success': False,
            'error': {
                'code': 'INTERNAL_SERVER_ERROR',
                'message': 'An internal server error occurred',
                'details': 'Please try again later or contact support',
                'timestamp': timezone.now().isoformat(),
                'request_id': request.META.get('REQUEST_ID', 'unknown')
            },
            'data': None
        }
        
        return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def handle_exception(self, exc):
        """Handle parsing and other exceptions."""
        if isinstance(exc, ParseError):
            return Response({
                'success': False,
                'error': {
                    'code': 'JSON_PARSE_ERROR',
                    'message': 'Invalid JSON in request body',
                    'details': str(exc),
                    'timestamp': timezone.now().isoformat(),
                    'request_id': 'unknown'
                },
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return super().handle_exception(exc)


class JobRetrieveView(APIView):
    """
    Retrieve job status and results.
    
    GET /jobs/{event_id}/
    Performance requirement: <100ms response time
    """
    
    def get(self, request, event_id) -> Response:
        """Retrieve job by event_id with status-specific response."""
        try:
            # 1. Convert UUID object to string if needed (<5ms)
            if isinstance(event_id, uuid.UUID):
                event_id_str = str(event_id)
            else:
                # Fallback for string input
                try:
                    uuid.UUID(event_id)
                    event_id_str = event_id
                except ValueError:
                    return self._invalid_uuid_response(request)
            
            # 2. Retrieve job from database (<20ms)
            job = self._get_job(event_id_str)
            if not job:
                return self._job_not_found_response(request)
            
            # 3. Serialize response data (<10ms)
            serializer = JobRetrieveSerializer(job)
            
            # 4. Return formatted response (<5ms)
            return self._success_response(serializer.data)
            
        except Exception as e:
            logger.exception(f"Unexpected error retrieving job {event_id_str if 'event_id_str' in locals() else event_id}: {str(e)}")
            return self._internal_error_response(request)
    
    def _get_job(self, event_id: str) -> Job:
        """Retrieve job by event_id with optimized query."""
        try:
            # Use select_related if we had foreign keys, but Job is self-contained
            job = Job.objects.get(event_id=event_id)
            return job
        except Job.DoesNotExist:
            return None
    
    def _success_response(self, data: Dict[str, Any]) -> Response:
        """Generate standardized success response."""
        response_data = {
            'success': True,
            'data': data
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def _job_not_found_response(self, request) -> Response:
        """Generate standardized job not found response."""
        response_data = {
            'success': False,
            'error': {
                'code': 'JOB_NOT_FOUND',
                'message': 'Job with specified event_id not found',
                'details': 'Please check the event_id and try again',
                'timestamp': timezone.now().isoformat(),
                'request_id': request.META.get('REQUEST_ID', 'unknown')
            },
            'data': None
        }
        
        return Response(response_data, status=status.HTTP_404_NOT_FOUND)
    
    def _invalid_uuid_response(self, request) -> Response:
        """Generate standardized invalid UUID response."""
        response_data = {
            'success': False,
            'error': {
                'code': 'INVALID_UUID',
                'message': 'Invalid event_id format',
                'details': 'event_id must be a valid UUID',
                'timestamp': timezone.now().isoformat(),
                'request_id': request.META.get('REQUEST_ID', 'unknown')
            },
            'data': None
        }
        
        return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
    
    def _internal_error_response(self, request) -> Response:
        """Generate standardized internal error response."""
        response_data = {
            'success': False,
            'error': {
                'code': 'INTERNAL_SERVER_ERROR',
                'message': 'An internal server error occurred',
                'details': 'Please try again later or contact support',
                'timestamp': timezone.now().isoformat(),
                'request_id': request.META.get('REQUEST_ID', 'unknown')
            },
            'data': None
        }
        
        return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)