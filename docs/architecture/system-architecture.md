# System Architecture - Guideline Ingestion API

## Overview
This document outlines the system architecture for the Django-based guideline ingestion API that processes guidelines through a two-step GPT chain to generate actionable checklists.

## Architecture Principles
- **Performance**: POST /jobs endpoint responds in <200ms
- **Scalability**: Concurrent job processing with horizontal scaling capability
- **Reliability**: Persistent job state with proper error handling and retries
- **Security**: Secure API key management and input validation
- **Observability**: Comprehensive logging and monitoring

## Component Architecture

### 1. API Layer (Django + DRF)
**Technology**: Django 5.1+ with Django REST Framework 3.15+
**Responsibilities**:
- HTTP request handling and validation
- Authentication and authorization
- Request/response serialization
- OpenAPI specification generation
- Rate limiting and throttling

**Key Components**:
- `JobCreateView`: Handles POST /jobs requests
- `JobDetailView`: Handles GET /jobs/{event_id} requests
- `JobSerializer`: Request/response data validation
- Middleware for logging and monitoring

### 2. Message Queue (Redis)
**Technology**: Redis 7.2+ as Celery broker and result backend
**Responsibilities**:
- Job queue management
- Task result storage
- Worker coordination
- Real-time job status updates

**Configuration**:
- Persistent storage for job durability
- Memory optimization for high throughput
- Connection pooling for performance

### 3. Async Workers (Celery)
**Technology**: Celery 5.4+ with Redis broker
**Responsibilities**:
- Background job processing
- GPT chain orchestration
- Error handling and retries
- Progress tracking and status updates

**Key Components**:
- `process_guideline_job`: Main job processing task
- `summarize_guidelines`: First GPT chain step
- `generate_checklist`: Second GPT chain step
- Error handlers and retry logic

### 4. Database Layer (PostgreSQL)
**Technology**: PostgreSQL 15+ with psycopg 3.2+ adapter
**Responsibilities**:
- Job metadata persistence
- Result storage
- Transaction management
- Query optimization

**Key Tables**:
- `jobs`: Job metadata, status, and results
- Indexes for performance optimization
- JSONB fields for flexible result storage

### 5. AI Integration (OpenAI API)
**Technology**: OpenAI Python SDK 1.57+
**Responsibilities**:
- Text summarization
- Checklist generation
- Rate limiting and error handling
- Response validation

## Data Flow Architecture

### Job Submission Flow
1. **Client Request**: POST /jobs with guideline text
2. **Validation**: Request validation and sanitization
3. **Job Creation**: Database record creation with PENDING status
4. **Queue Dispatch**: Job queued to Celery via Redis
5. **Response**: Immediate response with event_id (<200ms)

### Job Processing Flow
1. **Worker Pickup**: Celery worker receives job from Redis queue
2. **Status Update**: Job status changed to PROCESSING
3. **GPT Chain Step 1**: Summarize input guidelines
4. **GPT Chain Step 2**: Generate checklist from summary
5. **Result Storage**: Save results to PostgreSQL
6. **Status Update**: Job status changed to COMPLETED/FAILED

### Job Status Retrieval
1. **Client Request**: GET /jobs/{event_id}
2. **Database Query**: Fetch job status and results
3. **Response**: Return current status and results if available

## Performance Considerations

### Response Time Optimization
- **Async Processing**: Long-running tasks offloaded to workers
- **Database Indexing**: Optimized queries for job lookups
- **Connection Pooling**: Efficient database connections
- **Caching**: Redis for frequently accessed data

### Scalability Design
- **Horizontal Scaling**: Multiple Celery workers
- **Load Balancing**: Multiple Django instances behind load balancer
- **Database Optimization**: Read replicas for high-read scenarios
- **Queue Partitioning**: Topic-based queue distribution

### Concurrent Processing
- **Worker Isolation**: Independent job processing
- **Database Transactions**: ACID compliance for data integrity
- **Lock-free Design**: Optimistic concurrency control
- **Resource Management**: CPU and memory optimization

## Security Architecture

### API Security
- **Input Validation**: Comprehensive request validation
- **Rate Limiting**: Per-client request throttling
- **Authentication**: Token-based authentication
- **HTTPS**: Encrypted data transmission

### Data Security
- **Environment Variables**: Secure API key storage
- **Database Encryption**: Encrypted sensitive data storage
- **Access Control**: Role-based permissions
- **Audit Logging**: Comprehensive activity logging

## Error Handling & Resilience

### Retry Strategy
- **Exponential Backoff**: Progressive retry delays
- **Max Retries**: Configurable retry limits
- **Dead Letter Queue**: Failed job handling
- **Circuit Breaker**: API failure protection

### Monitoring & Alerting
- **Health Checks**: Service health monitoring
- **Metrics Collection**: Performance metrics
- **Error Tracking**: Comprehensive error logging
- **Alert Thresholds**: Proactive issue detection

## Technology Stack Rationale

### Django 5.1+ Selection
- **Mature Framework**: Battle-tested web framework
- **DRF Integration**: Excellent REST API support
- **ORM Capabilities**: Powerful database abstraction
- **Admin Interface**: Built-in administration
- **Security Features**: Comprehensive security features

### Celery 5.4+ Selection
- **Proven Scalability**: Production-ready task queue
- **Redis Integration**: Seamless broker integration
- **Monitoring Tools**: Flower and built-in monitoring
- **Flexible Routing**: Advanced task routing
- **Error Handling**: Robust retry mechanisms

### PostgreSQL 15+ Selection
- **JSONB Support**: Flexible result storage
- **Performance**: Excellent query optimization
- **Reliability**: ACID compliance and durability
- **Scalability**: Read replicas and partitioning
- **Advanced Features**: Full-text search, indexing

### Redis 7.2+ Selection
- **High Performance**: In-memory data structure store
- **Persistence**: Data durability options
- **Pub/Sub**: Real-time messaging capabilities
- **Clustering**: Horizontal scaling support
- **Memory Efficiency**: Optimized memory usage 