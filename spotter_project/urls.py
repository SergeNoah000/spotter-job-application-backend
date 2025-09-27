"""
URL configuration for spotter_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
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
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_root(request):
    """API root endpoint with available endpoints"""
    return Response({
        'message': 'Spotter Application API',
        'version': '1.0',
        'endpoints': {
            'auth': {
                'login': '/api/auth/login/',
                'logout': '/api/auth/logout/',
                'refresh': '/api/auth/refresh/',
                'change_password': '/api/auth/change-password/',
            },
            'users': {
                'profile': '/api/profile/',
                'users': '/api/users/',
                'companies': '/api/companies/',
                'dashboard_stats': '/api/dashboard/stats/',
            },
            'trips': {
                'trips': '/api/trips/',
                'vehicles': '/api/trips/vehicles/',
                'trip_planning': '/api/trips/plan/',
                'route_calculation': '/api/trips/route/calculate/',
                'statistics': '/api/trips/statistics/',
            },
            'eld_logs': {
                'logs': '/api/eld-logs/',
                'violations': '/api/eld-logs/violations/',
                'exports': '/api/eld-logs/exports/',
            }
        },
        'documentation': '/admin/doc/',
        'admin': '/admin/',
    })

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # API root
    path('api/', api_root, name='api_root'),
    
    # Authentication and user management
    path('api/accounts/', include('accounts.urls')),
    
    # Trips and vehicles
    path('api/trips/', include('trips.urls')),
    
    # ELD logs
    path('api/eld/', include('eld_logs.urls')),
    
    # Django allauth (if needed for social auth)
    path('accounts/', include('allauth.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
