"""
Celery configuration for guideline_ingestion project.

This module configures Celery for async task processing with Redis as broker.
Supports Django integration and proper task discovery.
"""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'guideline_ingestion.config.settings')

app = Celery('guideline_ingestion')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery configuration
app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=3,
    result_expires=3600,  # 1 hour
    task_soft_time_limit=900,  # 15 minutes soft limit
    task_time_limit=1800,  # 30 minutes hard limit
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_max_memory_per_child=200000,  # 200MB memory limit per worker
    task_compression='gzip',
    result_compression='gzip',
    # Fix for Celery 6.0 deprecation warning
    broker_connection_retry_on_startup=True,
    task_routes={
        'guideline_ingestion.jobs.tasks.process_guideline_job': {'queue': 'gpt_processing'},
        'guideline_ingestion.jobs.tasks.cleanup_old_jobs': {'queue': 'maintenance'},
        'guideline_ingestion.jobs.tasks.monitor_job_health': {'queue': 'monitoring'},
    },
    task_default_queue='default',
    task_create_missing_queues=True,
)

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery configuration."""
    print(f'Request: {self.request!r}')