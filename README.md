# Guideline Ingestion API

A high-performance Django REST API for asynchronous guideline processing using GPT-powered summarization and checklist generation.

## Quick Start

```bash
# Start the system
docker compose up -d

# Run tests  
docker compose exec app /app/test-docker.sh

# View API documentation
open http://localhost:8000/api/docs/
```

## API Endpoints

### Submit Job
```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -d '{"guidelines": "Patient care guidelines for emergency procedures..."}'
```

### Check Status
```bash
curl http://localhost:8000/jobs/{event_id}/
```

## Architecture Highlights

**Performance-First Design**: <200ms job submission, <100ms status retrieval via optimized PostgreSQL queries and Redis task queueing.

**Async Processing**: Django + Celery + Redis for scalable background job processing with comprehensive retry logic and error handling.

**TDD Approach**: 88% test coverage across 209 test cases including integration, performance, and infrastructure validation.

**Auto-Generated Documentation**: OpenAPI 3.0 spec generated from DRF decorators ensures documentation stays current with implementation.

## Key Design Decisions

- **Docker-First Development**: All services containerized for consistent environments and easy deployment
- **Database Constraints**: PostgreSQL check constraints ensure data integrity at the database level
- **Standardized Responses**: Consistent success/error response format across all endpoints following established patterns
- **Status-Specific Serialization**: Dynamic response fields based on job status reduce payload size and improve clarity

## AI Tool Usage

Claude Code assisted with:
- TDD test structure and comprehensive test coverage strategies
- OpenAPI documentation enhancement and DRF spectacular configuration  
- Performance optimization patterns and database query optimization
- Error handling standardization and response format consistency

Built with Django 5.1, PostgreSQL 15, Redis 7.2, Celery 5.4