"""
URL configuration for guideline_ingestion project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connections
from django.utils import timezone
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
import redis
from django.conf import settings

def health_check(request):
    """Health check endpoint for container orchestration."""
    try:
        # Check database connection
        db_conn = connections['default']
        db_conn.cursor()
        
        # Check Redis connection
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        
        return JsonResponse({
            'status': 'healthy',
            'database': 'connected',
            'redis': 'connected',
            'timestamp': timezone.now().isoformat(),
            'environment': settings.ENVIRONMENT
        })
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=503)

def readiness_check(request):
    """Readiness probe for Kubernetes-style orchestration."""
    try:
        # Check all critical services
        db_conn = connections['default']
        db_conn.cursor()
        
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        
        return JsonResponse({
            'status': 'ready',
            'services': {
                'database': 'ready',
                'redis': 'ready'
            },
            'timestamp': timezone.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({
            'status': 'not_ready',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=503)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health'),
    path('health/ready/', readiness_check, name='readiness'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('jobs/', include('jobs.urls')),
]