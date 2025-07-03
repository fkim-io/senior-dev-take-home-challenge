# Senior Dev Take-Home Challenge - Project Plan

## Overview
Building a minimal backend API with async job processing and GPT-chaining for guideline ingestion.

**Timeline:** 2-4 hours  
**Tech Stack:** Python + Django + Celery + Redis + PostgreSQL + OpenAI API  
**Development Approach:** Test-Driven Development (TDD) + Docker-First Development  
**Environment:** All development and testing done in containerized environment (no local Python venv needed)

## Core Requirements Summary
1. **POST /jobs** endpoint - queues job, returns event_id in <200ms
2. **GET /jobs/{event_id}** endpoint - returns job status and results
3. Worker processes jobs with 2-step GPT chain: summarize → generate checklist
4. Concurrent job processing with persistence
5. Docker-based deployment with single command bootstrap

## Deliverables Checklist
- [ ] Public GitHub repo with MIT/Apache-2 license
- [ ] One-command bootstrap: `docker compose up --build`
- [ ] Unit tests (~70% coverage)
- [ ] Auto-generated OpenAPI spec
- [ ] README (≤300 words) with design choices and AI tool usage
- [ ] Optional: Mermaid diagram generated with AI
- [ ] Proper .env handling with .gitignore

---

## Project Tasks (Chronological Order)

### 🧪 **TDD + Docker-First Benefits**
- **Higher Code Quality**: Tests drive design decisions and catch issues early
- **Faster Development**: Immediate feedback on code changes in realistic environment
- **Better Coverage**: Tests written alongside features ensure comprehensive coverage
- **Reduced Debugging**: Issues caught during development rather than after deployment
- **Refactoring Confidence**: Comprehensive test suite enables safe code improvements
- **Production Parity**: Development environment matches production deployment
- **Service Integration**: Early validation of service connectivity and dependencies

### Phase 1: Architecture & Design
**TASK-001: System Architecture Design**
- [x] Design overall system architecture
- [x] Define component interactions (API → Queue → Worker → Database)
- [x] Create Mermaid diagram for system flow
- [x] Document async job processing pattern

**TASK-002: API Design** ✅ COMPLETED
- [x] Define OpenAPI 3.0 specification
- [x] Design POST /jobs endpoint schema
- [x] Design GET /jobs/{event_id} endpoint schema
- [x] Define error response formats
- [x] Plan for <200ms response time requirement

**TASK-003: Database Design** ✅ COMPLETED
- [x] Design Job model schema
- [x] Define job statuses (PENDING, PROCESSING, COMPLETED, FAILED)
- [x] Design result storage structure
- [x] Plan for concurrent access patterns
- [x] Design database indexes for performance

*Deliverable*: `docs/architecture/database-design.md` - Comprehensive database design with Job model schema, PostgreSQL 15+ optimizations, JSONB result storage, concurrent access patterns, and performance indexing strategy. Includes atomic status updates, worker coordination, and <200ms creation performance requirements.

### Phase 2: Infrastructure Setup (Docker-First Approach)
**TASK-004: Project Initialization** ✅ COMPLETED
- [x] Initialize git repository
- [x] Set up MIT license
- [x] Create basic project structure
- [x] **Create requirements.txt with dependencies (no local virtual environment needed)**
- [x] **Prepare for Docker-based development environment**

**TASK-005: Docker Environment Setup** ✅ COMPLETED
- [x] Create Dockerfile for Django application
- [x] Create docker-compose.yml with services (app, redis, postgres, celery)
- [x] Configure environment variables
- [x] Set up .env template and .gitignore
- [x] Test basic container orchestration

**TASK-006: Environment Configuration & Docker Bootstrap** ✅ COMPLETED
- [x] Configure Django settings for different environments
- [x] Set up Redis connection configuration
- [x] Configure PostgreSQL database settings
- [x] Set up OpenAI API key management
- [x] Configure Celery broker and result backend
- [x] **Verify docker-compose.yml works with single command: `docker compose up --build`**
- [x] **Test complete bootstrap process - all services start correctly**
- [x] **Validate service connectivity (app connects to postgres, redis, celery worker starts)**
- [x] **Test basic Django admin and health endpoints in containerized environment**

### Phase 3: Core Development (TDD + Docker Environment)
**TASK-007: Testing Infrastructure Setup (Docker-based)** ✅ COMPLETED
- [x] Set up pytest and testing dependencies
- [x] Configure test settings to use containerized PostgreSQL test database
- [x] Set up test fixtures and factories
- [x] Configure test coverage reporting
- [x] Set up mocking for external dependencies (OpenAI API)
- [x] **Verify tests run correctly in Docker environment**
- [x] **Configure test database isolation between test runs**

**TASK-008: Django Project Setup (TDD)** ✅ COMPLETED
- [x] Write tests for Django project configuration
- [x] Create Django project and app structure
- [x] Configure Django settings.py
- [x] Set up database connection to containerized PostgreSQL
- [x] Create initial migrations and run them in Docker environment
- [x] Configure Django REST Framework
- [x] **Verify all setup tests pass in containerized environment**
- [x] **Test Django admin access via http://localhost:8000/admin/**

**TASK-009: Database Models (TDD)** *(COMPLETED)*
- [x] Write tests for Job model fields and validation
- [x] Write tests for model methods and properties
- [x] Write tests for model constraints and edge cases
- [x] Create Job model with fields (id, event_id, status, input_data, result, created_at, updated_at)
- [x] Implement model methods and properties
- [x] Create and run database migrations
- [x] Add model validators and constraints
- [x] Verify all model tests pass

**TASK-010: API Endpoints Implementation (TDD)** *(COMPLETED)*
- [x] Write tests for POST /jobs endpoint (success, validation, error cases)
- [x] Write tests for GET /jobs/{event_id} endpoint (found, not found, various statuses)
- [x] Write tests for request/response serializers
- [x] Write tests for error handling scenarios
- [x] Write tests for input validation
- [x] Write tests for <200ms response time requirement
- [x] Implement POST /jobs endpoint
- [x] Implement GET /jobs/{event_id} endpoint
- [x] Add request/response serializers
- [x] Implement proper error handling
- [x] Add input validation
- [x] Ensure <200ms response time for job submission
- [x] **Verify all API tests pass in containerized environment**
- [x] **Test endpoints manually via http://localhost:8000/jobs/ (POST) and http://localhost:8000/jobs/{event_id}/ (GET)**

**TASK-011: Celery Worker Setup (TDD)** ✅ *COMPLETED*
- [x] Write tests for Celery task configuration
- [x] Write tests for job processing task (mocked GPT calls)
- [x] Write tests for job status updates
- [x] Write tests for error handling and retry logic
- [x] Write tests for concurrent job processing
- [x] Configure Celery application
- [x] Create job processing task
- [x] Implement job status updates
- [x] Add error handling and retry logic
- [x] **Verify all Celery tests pass in containerized environment**
- [x] **Test Celery worker processes jobs by monitoring Docker logs**
- [x] **Verify Redis queue integration by checking redis-cli in container**

**TASK-012: GPT Integration (TDD)** ✅ *COMPLETED*
- [x] Write tests for OpenAI API client (mocked responses)
- [x] Write tests for summarization step with various inputs
- [x] Write tests for checklist generation step
- [x] Write tests for response parsing and validation
- [x] Write tests for rate limiting and error handling
- [x] Write tests for GPT chain integration
- [x] Implement OpenAI API client
- [x] Create prompts for summarization step
- [x] Create prompts for checklist generation step
- [x] Add response parsing and validation
- [x] Implement rate limiting and error handling
- [x] Add logging for GPT interactions
- [x] Implement two-step GPT chain: 
  - Step 1: Summarize input guidelines
  - Step 2: Generate checklist from summary
- [x] **Verify all GPT integration tests pass in containerized environment**
- [x] **Test end-to-end job processing: POST job → Celery worker → GPT chain → result storage**

### Phase 4: Integration & Performance Testing
**TASK-013: Integration Tests (Docker Environment)** ✅ *COMPLETED*
- [x] Test end-to-end job processing flow (API → Queue → Worker → Database)
- [x] Test concurrent job processing with multiple workers
- [x] **Test database persistence across container restarts (docker compose down/up)**
- [x] **Test service recovery and health checks**
- [x] Test error scenarios and recovery mechanisms
- [x] Test OpenAI API integration with real API calls (limited)
- [x] **Verify system handles container restart scenarios gracefully**
- [x] Verify overall system reliability and data consistency

**TASK-014: Test Suite Optimization & Performance Validation** ✅ *COMPLETED*
- [x] **Test Redundancy Analysis & Consolidation**
  - [x] Review 4,520+ lines of test code across 10 test files for redundancy
  - [x] Consolidate overlapping test coverage between files
  - [x] Merge test_end_to_end_gpt.py (112 lines) into test_integration.py
  - [x] Consolidate performance tests scattered across test_views.py and test_integration.py
  - [x] Optimize test infrastructure overlap between test_django_setup.py and test_infrastructure.py
- [x] **Performance & Load Testing Validation**
  - [x] Verify POST /jobs responds in <200ms under normal load (currently tested in multiple files)
  - [x] Test concurrent job submission (multiple simultaneous requests)
  - [x] Test queue performance under high load with Redis broker
  - [x] Test database query performance with large datasets (1000+ jobs)
  - [x] Test memory usage and resource consumption during peak loads
  - [x] Test system behavior at capacity limits and graceful degradation
- [x] **Test Coverage & Quality Assurance**
  - [x] Run full test suite and verify ~70% coverage achieved (88% achieved)
  - [x] Review test coverage reports and identify gaps in consolidated test suite
  - [x] Add missing tests for edge cases discovered during development
  - [x] Validate all test categories pass (unit, integration, performance) after consolidation
  - [x] Review test quality, maintainability, and execution speed after optimization
  - [x] Document optimized test execution procedures and categorization
- [x] **Test File Consolidation Plan**
  - [x] Keep: test_models.py, test_serializers.py, test_views.py, test_tasks.py, test_urls.py (core functionality)
  - [x] Consolidate: test_end_to_end_gpt.py → test_integration.py (eliminate 112-line redundancy)
  - [x] Merge: test_django_setup.py + test_infrastructure.py → test_setup_and_infrastructure.py
  - [x] Optimize: Remove duplicate performance tests, GPT integration tests, and API endpoint tests
  - [x] Target: Reduce from 10 files to 7 files while maintaining >70% coverage (achieved: 7 files, 88% coverage)

### Phase 5: Documentation & Deployment
**TASK-015: OpenAPI Specification & Documentation** ✅ COMPLETED
- [x] Generate OpenAPI 3.0 spec from Django REST Framework
- [x] Add comprehensive endpoint documentation
- [x] Include request/response examples
- [x] Document error codes and messages
- [x] Set up API documentation UI (Swagger/ReDoc)
- [x] Write concise README (≤300 words)
- [x] Document design choices and trade-offs
- [x] Explain where AI tools were used
- [x] Include setup and usage instructions
- [x] Add API endpoint examples
