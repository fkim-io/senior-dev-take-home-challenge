# API Design - Guideline Ingestion API

## Overview
This document defines the REST API design for the guideline ingestion system, focusing on job submission and status retrieval endpoints with sub-200ms response time requirements.

## Design Principles
- **Performance First**: POST /jobs responds in <200ms via async processing
- **RESTful Design**: HTTP verbs, status codes, and resource-oriented URLs
- **Consistent Responses**: Uniform JSON response structure across all endpoints
- **Error Transparency**: Clear error messages with actionable information
- **Validation**: Comprehensive input validation with detailed error feedback

## Base Configuration
- **Base URL**: `https://api.guideline-ingestion.com/v1`
- **Content-Type**: `application/json`
- **Response Format**: JSON
- **Authentication**: API Key via `Authorization: Bearer <token>` header
- **Rate Limiting**: 100 requests/minute per API key

## Core Endpoints

### 1. Job Submission Endpoint

#### `POST /jobs`
Submits guideline text for processing through the GPT chain.

**Request Schema**:
```json
{
  "guidelines": "string (required, 10-10000 characters)",
  "callback_url": "string (optional, valid HTTPS URL)",
  "priority": "string (optional, enum: 'low', 'normal', 'high', default: 'normal')",
  "metadata": "object (optional, key-value pairs for client tracking)"
}
```

**Validation Rules**:
- `guidelines`: Required, non-empty, 10-10,000 characters, plain text
- `callback_url`: Optional, must be valid HTTPS URL if provided
- `priority`: Optional, one of ['low', 'normal', 'high']
- `metadata`: Optional, max 10 key-value pairs, total size < 1KB

**Response Schema (Success - 201 Created)**:
```json
{
  "success": true,
  "data": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "PENDING",
    "created_at": "2024-01-15T10:30:00Z",
    "estimated_completion": "2024-01-15T10:31:30Z"
  },
  "message": "Job submitted successfully"
}
```

**Performance Requirements**:
- Response time: <200ms (95th percentile)
- Job queued to Redis immediately
- Database write optimized with minimal fields
- No blocking operations in request path

### 2. Job Status Endpoint

#### `GET /jobs/{event_id}`
Retrieves current job status and results if available.

**Path Parameters**:
- `event_id`: UUID v4 string (required)

**Response Schema (Success - 200 OK)**:
```json
{
  "success": true,
  "data": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "COMPLETED",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:31:45Z",
    "processing_time_seconds": 75.2,
    "result": {
      "summary": "Comprehensive summary of the provided guidelines...",
      "checklist": [
        {
          "id": 1,
          "title": "Verify data encryption standards",
          "description": "Ensure all sensitive data uses AES-256 encryption",
          "priority": "high",
          "category": "security"
        },
        {
          "id": 2,
          "title": "Implement access controls",
          "description": "Configure role-based access control for all endpoints",
          "priority": "medium",
          "category": "security"
        }
      ]
    },
    "metadata": {
      "gpt_model_used": "gpt-4",
      "tokens_consumed": 1250,
      "processing_steps": ["summarization", "checklist_generation"]
    }
  }
}
```

**Status-Specific Responses**:

**PENDING Status**:
```json
{
  "success": true,
  "data": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "PENDING",
    "created_at": "2024-01-15T10:30:00Z",
    "estimated_completion": "2024-01-15T10:31:30Z",
    "queue_position": 3
  }
}
```

**PROCESSING Status**:
```json
{
  "success": true,
  "data": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "PROCESSING",
    "created_at": "2024-01-15T10:30:00Z",
    "started_at": "2024-01-15T10:30:15Z",
    "current_step": "summarization",
    "progress_percentage": 45
  }
}
```

**FAILED Status**:
```json
{
  "success": true,
  "data": {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "FAILED",
    "created_at": "2024-01-15T10:30:00Z",
    "failed_at": "2024-01-15T10:30:45Z",
    "error": {
      "code": "GPT_API_ERROR",
      "message": "OpenAI API rate limit exceeded",
      "retry_after": "2024-01-15T10:35:00Z",
      "support_reference": "ERR-2024-001"
    }
  }
}
```

## Error Response Format

### Standard Error Response Structure
All error responses follow this consistent format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error description",
    "details": "Additional context or debugging information",
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_550e8400e29b41d4a716446655440000"
  },
  "data": null
}
```

### Error Codes and HTTP Status Mapping

#### Client Errors (4xx)

**400 Bad Request - VALIDATION_ERROR**:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "field_errors": {
        "guidelines": ["This field is required"],
        "callback_url": ["Invalid URL format"]
      }
    },
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_550e8400e29b41d4a716446655440000"
  }
}
```

**401 Unauthorized - AUTH_ERROR**:
```json
{
  "success": false,
  "error": {
    "code": "AUTH_ERROR",
    "message": "Authentication required",
    "details": "Valid API key must be provided in Authorization header"
  }
}
```

**404 Not Found - JOB_NOT_FOUND**:
```json
{
  "success": false,
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Job with specified event_id not found",
    "details": "Verify the event_id is correct and the job exists"
  }
}
```

**429 Too Many Requests - RATE_LIMIT_EXCEEDED**:
```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded",
    "details": "Maximum 100 requests per minute allowed",
    "retry_after": 45
  }
}
```

#### Server Errors (5xx)

**500 Internal Server Error - INTERNAL_ERROR**:
```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred",
    "details": "Please try again later or contact support",
    "support_reference": "ERR-2024-001"
  }
}
```

**503 Service Unavailable - SERVICE_OVERLOADED**:
```json
{
  "success": false,
  "error": {
    "code": "SERVICE_OVERLOADED",
    "message": "Service temporarily overloaded",
    "details": "Queue is at capacity, please try again in a few minutes",
    "retry_after": 120
  }
}
```

## Performance Requirements & Optimizations

### Response Time Targets
- **POST /jobs**: <200ms (95th percentile)
  - Request validation: <10ms
  - Database write: <50ms
  - Queue dispatch: <20ms
  - Response serialization: <10ms
  - Network overhead: <110ms

- **GET /jobs/{event_id}**: <100ms (95th percentile)
  - Database query: <30ms
  - Response serialization: <20ms
  - Network overhead: <50ms

### Database Query Optimization
```sql
-- Indexes for performance
CREATE INDEX idx_jobs_event_id ON jobs(event_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);

-- Optimized query for job status
SELECT 
  event_id, 
  status, 
  created_at, 
  updated_at, 
  result, 
  error_details
FROM jobs 
WHERE event_id = $1;
```

### Caching Strategy
- **Redis Caching**: Frequently accessed job statuses cached for 5 minutes
- **CDN**: Static API documentation and schemas
- **Database Connection Pooling**: Persistent connections to reduce overhead

### Concurrent Request Handling
- **Async Request Processing**: Non-blocking I/O for all operations
- **Database Connection Pooling**: 20 connections per Django instance
- **Queue Batching**: Multiple jobs queued in single Redis operation when possible

## API Versioning Strategy

### URL-Based Versioning
- Current: `/v1/jobs`
- Future: `/v2/jobs` (when breaking changes needed)

### Backward Compatibility
- v1 maintained for minimum 12 months after v2 release
- Deprecation warnings in response headers
- Migration guides provided for version transitions

## Security Considerations

### Authentication & Authorization
- API Key authentication required for all endpoints
- Rate limiting per API key (100 req/min)
- IP allowlisting available for enterprise customers

### Input Validation & Sanitization
- Comprehensive input validation on all fields
- HTML/script tag stripping from guidelines text
- SQL injection prevention via ORM
- XSS prevention in error messages

### Data Privacy
- Guidelines text encrypted at rest in database
- Results automatically expire after 30 days
- No sensitive data in log files
- GDPR compliance for data deletion

## Monitoring & Observability

### Metrics Collection
- Response time distribution (p50, p95, p99)
- Error rate by endpoint and error type
- Queue depth and processing time
- Database query performance

### Health Checks
- **GET /health**: Service health status
- **GET /health/ready**: Readiness probe for Kubernetes
- **GET /health/live**: Liveness probe for Kubernetes

### Logging Strategy
- Structured JSON logs
- Request ID tracking across services
- Error correlation with support references
- Performance metrics for optimization

## Future API Extensions

### Planned Features (v1.1)
- Batch job submission: `POST /jobs/batch`
- Job cancellation: `DELETE /jobs/{event_id}`
- Webhook notifications for job completion
- Custom GPT prompt templates

### Potential Features (v2.0)
- Streaming job results via WebSockets
- File upload support for document processing
- Multi-language guideline support
- Advanced result filtering and search 