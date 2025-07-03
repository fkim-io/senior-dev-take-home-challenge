# Database Design - Guideline Ingestion API

## Overview
This document details the database design for the guideline ingestion API, focusing on the Job model that tracks async job processing through the GPT chain workflow.

## Technology Stack
- **Database**: PostgreSQL 15+ for advanced JSONB features and performance
- **Adapter**: psycopg 3.2+ for optimal connection pooling and async support
- **ORM**: Django 5.1+ ORM with custom indexes and constraints
- **Connection Management**: PostgreSQL connection pooling for concurrent access

## Job Model Schema

### Primary Job Model
```python
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
                check=models.Q(retry_count__gte=0),
                name='jobs_retry_count_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(
                    models.Q(status='PENDING', started_at__isnull=True) |
                    models.Q(status='PROCESSING', started_at__isnull=False) |
                    models.Q(status__in=['COMPLETED', 'FAILED'])
                ),
                name='jobs_status_started_at_consistency'
            ),
        ]

    def __str__(self):
        return f"Job {self.event_id} ({self.status})"
```

### Job Status Enumeration
```python
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
```

## Result Storage Structure

### GPT Chain Output Schema
```python
# Expected result JSON structure stored in PostgreSQL JSONB field
RESULT_SCHEMA = {
    "summary": {
        "type": "string",
        "description": "GPT-generated summary of input guidelines",
        "max_length": 2000
    },
    "checklist": {
        "type": "array",
        "description": "GPT-generated actionable checklist items",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Unique checklist item ID"},
                "text": {"type": "string", "description": "Checklist item text"},
                "category": {"type": "string", "description": "Item category/topic"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]}
            },
            "required": ["id", "text", "category"]
        }
    },
    "metadata": {
        "type": "object",
        "description": "Processing metadata and GPT model info",
        "properties": {
            "model_version": {"type": "string"},
            "processing_time": {"type": "number"},
            "token_usage": {"type": "object"},
            "confidence_score": {"type": "number", "minimum": 0, "maximum": 1}
        }
    }
}

# Example result data:
{
    "summary": "Guidelines focus on code quality, security practices, and performance optimization...",
    "checklist": [
        {
            "id": "chk_001",
            "text": "Implement input validation for all API endpoints",
            "category": "security",
            "priority": "high"
        },
        {
            "id": "chk_002", 
            "text": "Add database indexes for frequently queried fields",
            "category": "performance",
            "priority": "medium"
        }
    ],
    "metadata": {
        "model_version": "gpt-4-turbo",
        "processing_time": 12.5,
        "token_usage": {
            "prompt_tokens": 1500,
            "completion_tokens": 800,
            "total_tokens": 2300
        },
        "confidence_score": 0.95
    }
}
```

### Input Data Schema
```python
# Input data structure stored in JSONField
INPUT_DATA_SCHEMA = {
    "guidelines": {
        "type": "string",
        "description": "Raw guideline text to process",
        "max_length": 50000
    },
    "metadata": {
        "type": "object",
        "description": "Client-provided metadata",
        "properties": {
            "source": {"type": "string", "description": "Guidelines source/origin"},
            "version": {"type": "string", "description": "Guidelines version"},
            "category": {"type": "string", "description": "Guidelines category"},
            "client_id": {"type": "string", "description": "Submitting client identifier"}
        }
    },
    "processing_options": {
        "type": "object",
        "description": "Job-specific processing configuration",
        "properties": {
            "max_checklist_items": {"type": "integer", "default": 20},
            "summary_length": {"type": "string", "enum": ["short", "medium", "long"], "default": "medium"},
            "priority_filter": {"type": "array", "items": {"type": "string"}}
        }
    }
}
```

## Concurrent Access Patterns

### 1. Atomic Status Updates
```python
# Safe concurrent status updates using database-level atomicity
def update_job_status(job_id: int, new_status: str, **updates) -> bool:
    """
    Atomically update job status with optimistic concurrency control.
    Returns True if update succeeded, False if job was modified concurrently.
    """
    with transaction.atomic():
        # Use select_for_update to prevent race conditions
        job = Job.objects.select_for_update().get(id=job_id)
        
        # Validate status transition
        if not is_valid_status_transition(job.status, new_status):
            raise ValueError(f"Invalid status transition: {job.status} → {new_status}")
        
        # Update with timestamp
        updated_fields = {
            'status': new_status,
            'updated_at': timezone.now(),
            **updates
        }
        
        # Add lifecycle timestamps
        if new_status == JobStatus.PROCESSING:
            updated_fields['started_at'] = timezone.now()
        elif new_status in JobStatus.get_terminal_statuses():
            updated_fields['completed_at'] = timezone.now()
        
        # Atomic update
        Job.objects.filter(id=job_id).update(**updated_fields)
        return True

def is_valid_status_transition(current: str, new: str) -> bool:
    """Validate job status state transitions."""
    valid_transitions = {
        JobStatus.PENDING: [JobStatus.PROCESSING, JobStatus.FAILED],
        JobStatus.PROCESSING: [JobStatus.COMPLETED, JobStatus.FAILED],
        JobStatus.FAILED: [JobStatus.PROCESSING],  # Retry
        JobStatus.COMPLETED: []  # Terminal state
    }
    return new in valid_transitions.get(current, [])
```

### 2. Worker Coordination
```python
# Prevent multiple workers from processing the same job
def claim_job_for_processing(job_id: int, worker_id: str) -> bool:
    """
    Atomically claim a job for processing by a specific worker.
    Returns True if claim succeeded, False if job already claimed.
    """
    try:
        with transaction.atomic():
            updated = Job.objects.filter(
                id=job_id,
                status=JobStatus.PENDING
            ).update(
                status=JobStatus.PROCESSING,
                started_at=timezone.now(),
                input_data=models.F('input_data').update({
                    'worker_id': worker_id,
                    'claimed_at': timezone.now().isoformat()
                })
            )
            return updated > 0
    except Exception:
        return False
```

### 3. Read Consistency
```python
# Ensure consistent reads for job status API
def get_job_status(event_id: uuid.UUID) -> Dict:
    """
    Get current job status with read consistency.
    Uses database-level isolation to prevent dirty reads.
    """
    job = Job.objects.select_related().get(event_id=event_id)
    
    return {
        'event_id': str(job.event_id),
        'status': job.status,
        'result': job.result if job.status == JobStatus.COMPLETED else None,
        'error': job.error_message if job.status == JobStatus.FAILED else None,
        'created_at': job.created_at.isoformat(),
        'updated_at': job.updated_at.isoformat()
    }
```

## Performance Indexes

### 1. Primary Performance Indexes
```sql
-- Event ID lookup (API primary use case)
CREATE UNIQUE INDEX jobs_event_id_idx ON jobs (event_id);

-- Status-based monitoring and filtering
CREATE INDEX jobs_status_idx ON jobs (status);

-- Time-based queries and pagination
CREATE INDEX jobs_created_at_idx ON jobs (created_at DESC);
CREATE INDEX jobs_updated_at_idx ON jobs (updated_at DESC);
```

### 2. Composite Indexes for Complex Queries
```sql
-- Status + time queries (dashboard, monitoring)
CREATE INDEX jobs_status_created_idx ON jobs (status, created_at DESC);

-- Failed job analysis and retry logic
CREATE INDEX jobs_status_retry_idx ON jobs (status, retry_count) 
WHERE status IN ('FAILED', 'PROCESSING');

-- Worker performance analysis
CREATE INDEX jobs_processing_time_idx ON jobs (started_at, completed_at)
WHERE completed_at IS NOT NULL;
```

### 3. JSONB Performance Indexes
```sql
-- Index specific JSONB fields for fast queries
CREATE INDEX jobs_result_summary_idx ON jobs USING GIN ((result->'summary'));
CREATE INDEX jobs_input_metadata_idx ON jobs USING GIN ((input_data->'metadata'));

-- Checklist item search
CREATE INDEX jobs_checklist_items_idx ON jobs USING GIN ((result->'checklist'));
```

### 4. Partial Indexes for Specific Use Cases
```sql
-- Active jobs only (PENDING/PROCESSING)
CREATE INDEX jobs_active_status_idx ON jobs (status, created_at) 
WHERE status IN ('PENDING', 'PROCESSING');

-- Recently completed jobs for client polling
CREATE INDEX jobs_recent_completed_idx ON jobs (completed_at DESC)
WHERE status = 'COMPLETED' AND completed_at > NOW() - INTERVAL '1 hour';

-- Error analysis and debugging
CREATE INDEX jobs_failed_recent_idx ON jobs (created_at DESC, error_message)
WHERE status = 'FAILED' AND created_at > NOW() - INTERVAL '24 hours';
```

## Database Configuration

### 1. PostgreSQL 15+ Optimizations
```sql
-- Connection pooling settings
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB

-- JSONB optimization
gin_pending_list_limit = 4MB

-- Query optimization
random_page_cost = 1.1  # SSD optimization
effective_io_concurrency = 200

-- Write performance
wal_buffers = 16MB
checkpoint_completion_target = 0.9
```

### 2. Django Database Configuration
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'guideline_ingestion'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'OPTIONS': {
            'sslmode': 'prefer',
        },
        'CONN_MAX_AGE': 60,  # Connection pooling
        'CONN_HEALTH_CHECKS': True,
    }
}

# Connection pooling with psycopg 3.2+
DATABASE_CONNECTION_POOLING = {
    'min_size': 5,
    'max_size': 20,
    'max_lifetime': 3600,
}
```

## Monitoring & Maintenance

### 1. Performance Monitoring Queries
```sql
-- Job processing performance
SELECT 
    status,
    COUNT(*) as job_count,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_processing_time,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (completed_at - started_at))) as p95_processing_time
FROM jobs 
WHERE completed_at IS NOT NULL 
    AND started_at IS NOT NULL
    AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY status;

-- Queue depth monitoring
SELECT 
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest_job
FROM jobs 
WHERE status IN ('PENDING', 'PROCESSING')
GROUP BY status;
```

### 2. Index Usage Analysis
```sql
-- Monitor index effectiveness
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes 
WHERE tablename = 'jobs'
ORDER BY idx_scan DESC;
```

### 3. Maintenance Tasks
```sql
-- Regular VACUUM and ANALYZE for JSONB performance
VACUUM ANALYZE jobs;

-- Reindex periodically for optimal performance
REINDEX INDEX CONCURRENTLY jobs_event_id_idx;

-- Clean up old completed jobs (retention policy)
DELETE FROM jobs 
WHERE status = 'COMPLETED' 
    AND completed_at < NOW() - INTERVAL '30 days';
```

## Migration Strategy

### 1. Initial Migration
```python
# Django migration for Job model
class Migration(migrations.Migration):
    initial = True
    
    dependencies = []
    
    operations = [
        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.BigAutoField(primary_key=True)),
                ('event_id', models.UUIDField(default=uuid.uuid4, unique=True)),
                ('status', models.CharField(max_length=20, choices=JobStatus.choices, default='PENDING')),
                ('input_data', models.JSONField()),
                ('result', models.JSONField(null=True, blank=True, default=dict)),
                ('error_message', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('started_at', models.DateTimeField(null=True, blank=True)),
                ('completed_at', models.DateTimeField(null=True, blank=True)),
                ('retry_count', models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                'db_table': 'jobs',
                'ordering': ['-created_at'],
            },
        ),
        # Add all indexes as separate operations for better control
        migrations.AddIndex(
            model_name='job',
            index=models.Index(fields=['event_id'], name='jobs_event_id_idx'),
        ),
        # ... additional index operations
    ]
```

### 2. Performance Testing
```python
# Database performance test cases
def test_job_creation_performance():
    """Test job creation meets <200ms requirement."""
    start_time = time.time()
    
    job = Job.objects.create(
        input_data={'guidelines': 'test guidelines'},
        status=JobStatus.PENDING
    )
    
    creation_time = (time.time() - start_time) * 1000
    assert creation_time < 200, f"Job creation took {creation_time}ms, exceeds 200ms limit"

def test_concurrent_status_updates():
    """Test concurrent status updates don't cause data corruption."""
    job = Job.objects.create(input_data={'guidelines': 'test'})
    
    # Simulate concurrent workers trying to claim the same job
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(claim_job_for_processing, job.id, f'worker_{i}')
            for i in range(10)
        ]
        
        results = [f.result() for f in futures]
        
    # Only one worker should successfully claim the job
    assert sum(results) == 1, "Multiple workers claimed the same job"
```

This database design provides a robust foundation for the guideline ingestion API with proper performance optimization, concurrent access safety, and scalability for the expected workload. 