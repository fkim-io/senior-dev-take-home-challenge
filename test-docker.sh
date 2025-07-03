#!/bin/bash
# Test runner script for Docker environment
# Ensures proper environment setup for running tests in containerized environment

set -e

# Set environment variables for testing
export PYTHONPATH=/app/guideline_ingestion:/app
export DJANGO_SETTINGS_MODULE=config.test_settings

# Change to app directory
cd /app

# Run tests with proper configuration
python -m pytest "$@"