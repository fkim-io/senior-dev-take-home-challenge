"""
Django app configuration for jobs application.
"""

from django.apps import AppConfig


class JobsConfig(AppConfig):
    """Configuration for jobs application."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'guideline_ingestion.jobs'
    verbose_name = 'Job Management'