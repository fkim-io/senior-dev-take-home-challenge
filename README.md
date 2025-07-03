# Guideline Ingestion API

Async backend API for guideline processing with two-step GPT chain (summarize → generate checklist).

## Quick Start

```bash
# One-command bootstrap
docker compose up --build

# Run tests (88% coverage)
docker compose exec app /app/test-docker.sh

# API docs: http://localhost:8000/api/docs/
```

## API Usage

**Submit Job** (returns event_id in <200ms):
```bash
curl -X POST http://localhost:8000/jobs/ \
  -H "Content-Type: application/json" \
  -d '{"guidelines": "Emergency triage protocols..."}'
```

**Check Status**:
```bash
curl http://localhost:8000/jobs/{event_id}/
```

## Architecture

**Stack**: Django 5.1 + Celery + Redis + PostgreSQL + OpenAI GPT-4

**Design Choices**:
- **Async Processing**: Celery workers handle GPT chain concurrently
- **Fast Response**: Job queuing returns immediately, processing happens in background  
- **Data Integrity**: PostgreSQL constraints + atomic status updates prevent race conditions
- **Status-Aware**: Response fields vary by job status (PENDING/PROCESSING/COMPLETED/FAILED)

**Performance**: 
- POST /jobs: <200ms (requirement met)
- GET /jobs/{id}: <100ms
- Concurrent job processing with retry logic

## AI Tool Usage

Used Cursor/Claude for:
- TDD test structure and comprehensive coverage
- OpenAPI spec generation and DRF configuration
- Performance optimization patterns
- Error handling standardization

**Auto-generated OpenAPI spec** available at `/api/docs/` with comprehensive examples and error documentation.