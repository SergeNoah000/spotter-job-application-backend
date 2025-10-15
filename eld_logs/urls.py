from django.urls import path
from . import views

app_name = 'eld_logs'

urlpatterns = [
    # ELD Logs
    path('logs/', views.ELDLogListCreateView.as_view(), name='eld_log_list_create'),
    path('logs/<uuid:pk>/', views.ELDLogDetailView.as_view(), name='eld_log_detail'),
    
    # HOS Status Management (nouveaux endpoints)
    path('hos/status/change/', views.change_duty_status, name='change_duty_status'),
    path('hos/status/current/', views.get_current_hos_status, name='get_current_hos_status'),
    path('hos/status/entries/', views.get_duty_status_entries, name='get_duty_status_entries'),
    path('hos/certify/', views.certify_daily_log, name='certify_daily_log'),
    
    # Anciens endpoints (à garder pour compatibilité)
    path('hos/status-change/', views.create_hos_status_change, name='create_hos_status_change'),
    path('hos/current-status/', views.get_driver_current_hos_status, name='get_driver_current_hos_status'),
    path('logs/daily/', views.get_driver_daily_logs, name='get_driver_daily_logs'),
    
    # HOS Violations
    path('violations/', views.HOSViolationListView.as_view(), name='hos_violation_list'),
    path('violations/<uuid:pk>/', views.HOSViolationDetailView.as_view(), name='hos_violation_detail'),
    
    # ELD Exports
    path('exports/', views.ELDExportListCreateView.as_view(), name='eld_export_list_create'),
    path('exports/<uuid:pk>/', views.ELDExportDetailView.as_view(), name='eld_export_detail'),
    
    # Trip integration
    path('generate-from-trip/<uuid:trip_id>/', views.generate_eld_from_trip, name='generate_eld_from_trip'),
]