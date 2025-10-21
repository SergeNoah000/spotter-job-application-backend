from django.urls import path
from . import views

app_name = 'eld_logs'

urlpatterns = [
    # ELD Logs
    path('logs/', views.ELDLogListCreateView.as_view(), name='eld_log_list_create'),
    path('logs/<uuid:pk>/', views.ELDLogDetailView.as_view(), name='eld_log_detail'),
    
    # Driver Activity (indépendant des voyages)
    path('activity/current/', views.get_driver_activity, name='get_driver_activity'),
    path('activity/change-status/', views.change_duty_status, name='change_duty_status'),
    path('activity/segments/<uuid:segment_id>/link-trip/', views.link_segment_to_trip, name='link_segment_to_trip'),
    
    # HOS Status Management
    path('hos/status-change/', views.create_hos_status_change, name='create_hos_status_change'),
    path('hos/current-status/', views.get_driver_current_hos_status, name='get_driver_current_hos_status'),
    path('logs/daily/', views.get_driver_daily_logs, name='get_driver_daily_logs'),
    
    # HOS Violations (placeholder)
    path('violations/', views.HOSViolationListView.as_view(), name='hos_violation_list'),
    path('violations/<uuid:pk>/', views.HOSViolationDetailView.as_view(), name='hos_violation_detail'),
    
    # ELD Exports (placeholder)
    path('exports/', views.ELDExportListCreateView.as_view(), name='eld_export_list_create'),
    path('exports/<uuid:pk>/', views.ELDExportDetailView.as_view(), name='eld_export_detail'),
    
    # Trip integration
    path('generate-from-trip/<uuid:trip_id>/', views.generate_eld_from_trip, name='generate_eld_from_trip'),
]