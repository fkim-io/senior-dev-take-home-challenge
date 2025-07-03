# Async Job Processing Pattern - Guideline Ingestion API

## Overview
This document details the asynchronous job processing pattern implemented for the guideline ingestion API, ensuring responsive API performance while handling long-running GPT processing tasks.

## Pattern Motivation

### Performance Requirements
- **Sub-200ms Response**: POST /jobs must respond within 200ms
- **Long Processing**: GPT chain processing can take 10-60 seconds
- **Concurrent Handling**: Multiple jobs processed simultaneously
- **Resource Efficiency**: Non-blocking request handling

### Traditional vs Async Approach

#### Traditional Synchronous Approach (❌ Not Suitable)
```
Client Request → Process GPT Chain → Return Results
     |              (10-60 seconds)         |
     └─────────────── 10-60 seconds ────────┘
```

#### Async Pattern (✅ Implemented)
```
Client Request → Queue Job → Return Event ID
     |              |            |
     └── <200ms ─────┘            └── Immediate Response

Background: Worker → Process GPT → Store Results
                  (10-60 seconds)
```

## Implementation Architecture

### 1. Job Lifecycle States

```
PENDING → PROCESSING → COMPLETED
   ↓           ↓           ↑
   └─────── FAILED ────────┘
```

#### State Descriptions
- **PENDING**: Job queued, waiting for worker
- **PROCESSING**: Worker actively processing job
- **COMPLETED**: Job finished successfully with results
- **FAILED**: Job failed due to error (with error details)

### 2. Component Responsibilities

#### API Layer (Django + DRF)
```python
# Job Submission Endpoint
POST /jobs
├── Request Validation (input sanitization)
├── Job Record Creation (DB: status=PENDING)
├── Queue Job (Celery task dispatch)
└── Return Event ID (<200ms)

# Job Status Endpoint  
GET /jobs/{event_id}
├── Database Query (fetch job by event_id)
└── Return Status + Results (if available)
```

#### Queue Layer (Redis + Celery)
```python
# Task Definition
@celery.task(bind=True, max_retries=3)
def process_guideline_job(self, job_id, guideline_text):
    try:
        # Update status to PROCESSING
        # Execute GPT chain
        # Store results and mark COMPLETED
    except Exception as exc:
        # Retry logic or mark FAILED
```

#### Worker Layer (Celery Workers)
```python
# GPT Processing Chain
def process_job(job_id, guideline_text):
    update_job_status(job_id, 'PROCESSING')
    
    # Step 1: Summarize guidelines
    summary = gpt_summarize(guideline_text)
    
    # Step 2: Generate checklist from summary
    checklist = gpt_generate_checklist(summary)
    
    # Store results
    save_job_results(job_id, {
        'summary': summary,
        'checklist': checklist
    })
    
    update_job_status(job_id, 'COMPLETED')
```

## Data Flow Patterns

### 1. Job Submission Pattern

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │    │   Django    │    │ PostgreSQL  │    │    Redis    │
│             │    │     API     │    │     DB      │    │   Queue     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │
       │ POST /jobs       │                  │                  │
       │ guideline_text   │                  │                  │
       ├─────────────────▶│                  │                  │
       │                  │ INSERT job       │                  │
       │                  │ status=PENDING   │                  │
       │                  ├─────────────────▶│                  │
       │                  │ job_id           │                  │
       │                  │◀─────────────────┤                  │
       │                  │ QUEUE task       │                  │
       │                  │ job_id + data    │                  │
       │                  ├──────────────────────────────────────▶│
       │ 200 OK           │                  │                  │
       │ event_id         │                  │                  │
       │◀─────────────────┤                  │                  │
       │                  │                  │                  │
```

### 2. Job Processing Pattern

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Celery    │    │ PostgreSQL  │    │   OpenAI    │    │    Redis    │
│   Worker    │    │     DB      │    │    API      │    │   Queue     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │
       │ DEQUEUE task     │                  │                  │
       │◀─────────────────────────────────────────────────────────┤
       │ UPDATE status    │                  │                  │
       │ PROCESSING       │                  │                  │
       ├─────────────────▶│                  │                  │
       │ GPT summarize    │                  │                  │
       │ request          │                  │                  │
       ├──────────────────────────────────────▶│                  │
       │ summary response │                  │                  │
       │◀──────────────────────────────────────┤                  │
       │ GPT checklist    │                  │                  │
       │ request          │                  │                  │
       ├──────────────────────────────────────▶│                  │
       │ checklist response│                  │                  │
       │◀──────────────────────────────────────┤                  │
       │ UPDATE results   │                  │                  │
       │ status=COMPLETED │                  │                  │
       ├─────────────────▶│                  │                  │
       │                  │                  │                  │
```

### 3. Job Status Retrieval Pattern

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Client    │    │   Django    │    │ PostgreSQL  │
│             │    │     API     │    │     DB      │
└─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │
       │ GET /jobs/       │                  │
       │ {event_id}       │                  │
       ├─────────────────▶│                  │
       │                  │ SELECT job       │
       │                  │ WHERE event_id   │
       │                  ├─────────────────▶│
       │                  │ job data         │
       │                  │◀─────────────────┤
       │ 200 OK           │                  │
       │ status + results │                  │
       │◀─────────────────┤                  │
       │                  │                  │
```

## Error Handling & Recovery

### 1. Retry Strategy

```python
@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def process_guideline_job(self, job_id, guideline_text):
    try:
        # Job processing logic
        return process_job(job_id, guideline_text)
    except OpenAIError as exc:
        # Retry for API errors
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        else:
            # Mark job as failed after max retries
            mark_job_failed(job_id, str(exc))
    except Exception as exc:
        # Mark job as failed for unexpected errors
        mark_job_failed(job_id, str(exc))
```

### 2. Dead Letter Queue Pattern

```
Normal Queue → Worker Processing → Success
     │              │
     └── Failed ─────┼──→ Retry Queue → Worker → Success
                     │                   │
                     └── Max Retries ────┼──→ Dead Letter Queue
                                         │
                                         └── Manual Review
```

### 3. Job Timeout Handling

```python
# Worker configuration
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 minutes soft limit

@celery.task(bind=True, time_limit=300, soft_time_limit=240)
def process_guideline_job(self, job_id, guideline_text):
    try:
        # Processing with timeout awareness
        return process_with_timeout(job_id, guideline_text)
    except SoftTimeLimitExceeded:
        # Graceful cleanup before hard timeout
        mark_job_failed(job_id, "Processing timeout")
```

## Performance Optimizations

### 1. Database Query Optimization

```sql
-- Index for fast job lookups
CREATE INDEX idx_jobs_event_id ON jobs(event_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);

-- Optimized status query
SELECT id, event_id, status, result, created_at, updated_at 
FROM jobs 
WHERE event_id = %s;
```

### 2. Redis Configuration

```python
# Connection pooling
CELERY_BROKER_POOL_LIMIT = 10
CELERY_BROKER_CONNECTION_MAX_RETRIES = 3

# Result backend optimization
CELERY_RESULT_EXPIRES = 3600  # 1 hour
CELERY_RESULT_COMPRESSION = 'gzip'
```

### 3. Worker Scaling

```yaml
# docker-compose.yml worker scaling
services:
  worker:
    replicas: 3  # Multiple worker instances
    environment:
      CELERY_CONCURRENCY: 2  # 2 concurrent tasks per worker
```

## Monitoring & Observability

### 1. Job Status Metrics

```python
# Custom metrics for monitoring
JOB_PROCESSING_TIME = Histogram('job_processing_seconds')
JOB_SUCCESS_RATE = Counter('job_success_total')
JOB_FAILURE_RATE = Counter('job_failure_total')
QUEUE_SIZE = Gauge('queue_size_current')
```

### 2. Health Checks

```python
# API health check endpoint
GET /health
{
    "status": "healthy",
    "database": "connected",
    "redis": "connected",
    "workers": {
        "active": 3,
        "total": 5
    },
    "queue_size": 12
}
```

### 3. Logging Strategy

```python
import logging

logger = logging.getLogger(__name__)

def process_job(job_id, guideline_text):
    logger.info(f"Starting job processing: {job_id}")
    
    try:
        # Processing logic with detailed logging
        logger.info(f"GPT summarization started: {job_id}")
        summary = gpt_summarize(guideline_text)
        logger.info(f"GPT summarization completed: {job_id}")
        
        logger.info(f"GPT checklist generation started: {job_id}")
        checklist = gpt_generate_checklist(summary)
        logger.info(f"GPT checklist generation completed: {job_id}")
        
        logger.info(f"Job processing completed successfully: {job_id}")
        
    except Exception as e:
        logger.error(f"Job processing failed: {job_id}, error: {str(e)}")
        raise
```

## Best Practices

### 1. Idempotency
- Jobs can be safely retried without side effects
- Database operations use proper transaction handling
- External API calls include idempotency keys where possible

### 2. Resource Management
- Worker process limits to prevent memory leaks
- Database connection pooling
- Redis connection reuse

### 3. Graceful Degradation
- Fallback mechanisms for external API failures
- Queue overflow protection
- Worker overload detection

### 4. Testing Strategy
- Unit tests for individual task functions
- Integration tests for full job flow
- Load tests for concurrent processing
- Mocked external dependencies for reliable testing

## Security Considerations

### 1. Input Validation
- Sanitize guideline text input
- Validate job parameters
- Prevent injection attacks

### 2. API Key Management
- Secure OpenAI API key storage
- Rate limiting for API calls
- API key rotation strategy

### 3. Data Privacy
- Secure storage of guideline content
- Data retention policies
- Audit logging for compliance 