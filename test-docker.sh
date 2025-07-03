#!/bin/bash
# Test runner script for Docker environment
# Ensures proper environment setup for running tests in containerized environment

set -e

# Set environment variables for testing
export PYTHONPATH=/app/guideline_ingestion:/app
export DJANGO_SETTINGS_MODULE=config.test_settings

# Change to the guideline_ingestion directory where Django project is located
cd /app/guideline_ingestion

echo "Running test suite with coverage reporting..."
echo "=========================================="

# Run tests with proper configuration
python -m pytest "$@"

echo ""
echo "Coverage Summary:"
echo "=================="

# Display coverage report
python -m coverage report --show-missing

echo ""
echo "HTML coverage report generated in htmlcov/ directory"