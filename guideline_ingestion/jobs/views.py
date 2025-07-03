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
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

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
    
    @extend_schema(
        operation_id="jobs_create",
        summary="Create new job for guideline processing",
        description=(
            "Submit guidelines for processing through the GPT chain. "
            "The job will be queued for asynchronous processing and return an event_id for tracking. "
            "**Performance requirement**: <200ms response time (95th percentile)."
        ),
        request=JobCreateSerializer,
        responses={
            201: OpenApiResponse(
                description="Job created successfully",
                examples=[
                    OpenApiExample(
                        "Success Response",
                        value={
                            "success": True,
                            "data": {
                                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                                "status": "PENDING",
                                "created_at": "2024-01-15T10:30:00Z",
                                "estimated_completion": "2024-01-15T10:31:30Z"
                            },
                            "message": "Job submitted successfully"
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Validation error",
                examples=[
                    OpenApiExample(
                        "Field Validation Error",
                        value={
                            "success": False,
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Request validation failed",
                                "details": {
                                    "field_errors": {
                                        "guidelines": ["This field is required."],
                                        "callback_url": ["Enter a valid URL."]
                                    }
                                },
                                "timestamp": "2024-01-15T10:30:00Z",
                                "request_id": "req_550e8400e29b41d4a716446655440000"
                            },
                            "data": None
                        }
                    ),
                    OpenApiExample(
                        "JSON Parse Error",
                        value={
                            "success": False,
                            "error": {
                                "code": "JSON_PARSE_ERROR",
                                "message": "Invalid JSON in request body",
                                "details": "Expecting ',' delimiter: line 1 column 25 (char 24)",
                                "timestamp": "2024-01-15T10:30:00Z",
                                "request_id": "unknown"
                            },
                            "data": None
                        }
                    )
                ]
            ),
            429: OpenApiResponse(
                description="Rate limit exceeded",
                examples=[
                    OpenApiExample(
                        "Rate Limit Error",
                        value={
                            "success": False,
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": "Rate limit exceeded",
                                "details": "Maximum 100 requests per minute allowed",
                                "timestamp": "2024-01-15T10:30:00Z",
                                "request_id": "req_550e8400e29b41d4a716446655440000"
                            },
                            "data": None
                        }
                    )
                ]
            ),
            500: OpenApiResponse(
                description="Internal server error",
                examples=[
                    OpenApiExample(
                        "Internal Server Error",
                        value={
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
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                "Basic Job Submission",
                value={
                    "guidelines": "Patient care guidelines for emergency room triage procedures. Patients with chest pain should be immediately assessed for cardiac symptoms."
                }
            ),
            OpenApiExample(
                "Job with Callback and Metadata",
                value={
                    "guidelines": "Healthcare protocol for medication administration. All medications must be double-checked before administration.",
                    "callback_url": "https://example.com/webhooks/job-completed",
                    "priority": "high",
                    "metadata": {
                        "department": "cardiology",
                        "version": "2.1",
                        "requester": "dr.smith@hospital.com"
                    }
                }
            )
        ],
        tags=["Jobs"]
    )
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
    
    @extend_schema(
        operation_id="jobs_retrieve",
        summary="Retrieve job status and results",
        description=(
            "Retrieve the current status and results of a job by its event_id. "
            "Response fields vary based on job status (PENDING, PROCESSING, COMPLETED, FAILED). "
            "**Performance requirement**: <100ms response time (95th percentile)."
        ),
        responses={
            200: OpenApiResponse(
                description="Job retrieved successfully",
                examples=[
                    OpenApiExample(
                        "PENDING Job Status",
                        value={
                            "success": True,
                            "data": {
                                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                                "status": "PENDING",
                                "created_at": "2024-01-15T10:30:00Z",
                                "updated_at": "2024-01-15T10:30:00Z",
                                "estimated_completion": "2024-01-15T10:31:30Z",
                                "queue_position": 3
                            }
                        }
                    ),
                    OpenApiExample(
                        "PROCESSING Job Status",
                        value={
                            "success": True,
                            "data": {
                                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                                "status": "PROCESSING",
                                "created_at": "2024-01-15T10:30:00Z",
                                "updated_at": "2024-01-15T10:30:45Z",
                                "started_at": "2024-01-15T10:30:45Z",
                                "estimated_completion": "2024-01-15T10:31:30Z",
                                "current_step": "summarization",
                                "retry_count": 0
                            }
                        }
                    ),
                    OpenApiExample(
                        "COMPLETED Job Status",
                        value={
                            "success": True,
                            "data": {
                                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                                "status": "COMPLETED",
                                "created_at": "2024-01-15T10:30:00Z",
                                "updated_at": "2024-01-15T10:31:15Z",
                                "started_at": "2024-01-15T10:30:45Z",
                                "completed_at": "2024-01-15T10:31:15Z",
                                "estimated_completion": "2024-01-15T10:31:30Z",
                                "processing_time_seconds": 30.5,
                                "retry_count": 0,
                                "result": {
                                    "summary": "Patient care guidelines for emergency room triage...",
                                    "checklist": [
                                        "Assess chest pain severity",
                                        "Check vital signs",
                                        "Perform ECG within 10 minutes"
                                    ]
                                },
                                "metadata": {
                                    "gpt_model_used": "gpt-4",
                                    "tokens_consumed": 1250,
                                    "processing_steps": ["summarization", "checklist_generation"]
                                }
                            }
                        }
                    ),
                    OpenApiExample(
                        "FAILED Job Status",
                        value={
                            "success": True,
                            "data": {
                                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                                "status": "FAILED",
                                "created_at": "2024-01-15T10:30:00Z",
                                "updated_at": "2024-01-15T10:30:55Z",
                                "started_at": "2024-01-15T10:30:45Z",
                                "completed_at": "2024-01-15T10:30:55Z",
                                "processing_time_seconds": 10.0,
                                "retry_count": 2,
                                "error_message": "GPT API rate limit exceeded. Maximum retries reached."
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Invalid event_id format",
                examples=[
                    OpenApiExample(
                        "Invalid UUID Error",
                        value={
                            "success": False,
                            "error": {
                                "code": "INVALID_UUID",
                                "message": "Invalid event_id format",
                                "details": "event_id must be a valid UUID",
                                "timestamp": "2024-01-15T10:30:00Z",
                                "request_id": "req_550e8400e29b41d4a716446655440000"
                            },
                            "data": None
                        }
                    )
                ]
            ),
            404: OpenApiResponse(
                description="Job not found",
                examples=[
                    OpenApiExample(
                        "Job Not Found Error",
                        value={
                            "success": False,
                            "error": {
                                "code": "JOB_NOT_FOUND",
                                "message": "Job with specified event_id not found",
                                "details": "Please check the event_id and try again",
                                "timestamp": "2024-01-15T10:30:00Z",
                                "request_id": "req_550e8400e29b41d4a716446655440000"
                            },
                            "data": None
                        }
                    )
                ]
            ),
            500: OpenApiResponse(
                description="Internal server error",
                examples=[
                    OpenApiExample(
                        "Internal Server Error",
                        value={
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
                    )
                ]
            )
        },
        tags=["Jobs"]
    )
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