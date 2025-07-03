# Guideline Ingestion API

Async backend API for guideline processing with two-step GPT chain (summarize → generate checklist).

## Quick Start

```bash
# Create .env file with required environment variables first
cp .env.example .env  # Edit with your OpenAI API key

# One-command bootstrap
docker compose up --build

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

## Architecture & Design Choices

**Stack**: Django 5.1 + Celery + Redis + PostgreSQL + OpenAI GPT-4

**Key Design Decisions**:
- **Async Processing**: Celery workers handle GPT chain concurrently, job submission returns immediately
- **Fast Response**: POST /jobs <200ms (requirement met), background processing decoupled
- **Data Integrity**: PostgreSQL constraints + atomic status updates prevent race conditions
- **Status-Aware Serialization**: Response fields vary by job status (PENDING/PROCESSING/COMPLETED/FAILED)
- **Error Resilience**: Exponential backoff retry, rate limiting, comprehensive error categorization

**Performance Optimizations**:
- Database indexes for status queries
- Redis result caching
- GPT client with memory tracking
- Connection pooling

## AI Tool Usage

Used **Cursor/Claude** extensively for:
- **TDD Implementation**: Generated comprehensive test suite achieving 97% coverage (329 tests)
- **OpenAPI Spec Generation**: Auto-generated documentation with examples and error schemas
- **Performance Patterns**: Database optimization, async processing patterns, retry logic
- **Error Handling**: Robust categorization of GPT API errors vs system errors
- **Code Quality**: Consistent Django patterns, proper serialization, atomic transactions

**Auto-generated OpenAPI spec** available at `/api/docs/` with comprehensive examples and error documentation.