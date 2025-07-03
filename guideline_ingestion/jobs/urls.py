"""
URL patterns for jobs API.

This module contains URL routing for job creation and retrieval endpoints
with proper UUID validation and namespacing.
"""

from django.urls import path

from guideline_ingestion.jobs.views import JobCreateView, JobRetrieveView

app_name = 'jobs'

urlpatterns = [
    # POST /jobs/ - Job submission endpoint
    path('', JobCreateView.as_view(), name='job-create'),
    
    # GET /jobs/{event_id}/ - Job status and result retrieval endpoint
    path('<flexible_uuid:event_id>/', JobRetrieveView.as_view(), name='job-retrieve'),
]