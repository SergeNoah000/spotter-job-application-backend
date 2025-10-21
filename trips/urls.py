from django.urls import path
from . import views

app_name = 'trips'

urlpatterns = [
    # Dashboard endpoints
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),
    path('dashboard/hos-status/', views.hos_status, name='hos_status'),
    path('dashboard-data/', views.get_dashboard_data, name='dashboard-data'),
    
    # Géolocalisation et navigation
    path('locations/search/', views.search_locations, name='search_locations'),
    path('locations/reverse-geocode/', views.get_current_location_address, name='reverse_geocode'),
    path('navigation/calculate-route/', views.calculate_route_with_navigation, name='calculate_route'),
    
    # Vehicles - Routes spécifiques AVANT les routes avec paramètres
    path('vehicles/', views.VehicleListCreateView.as_view(), name='vehicle_list_create'),
    
    # Export des véhicules (DOIT être avant vehicles/<uuid:pk>/)
    path('vehicles/export/', views.export_vehicles, name='export_vehicles'),
    
    # Statistiques dashboard admin
    path('vehicles/dashboard-stats/', views.dashboard_vehicle_stats, name='dashboard_vehicle_stats'),
    path('vehicles/statistics/', views.vehicle_statistics, name='vehicle_statistics'),
    
    # Ancienne assignation véhicules-conducteurs (à supprimer après migration)
    path('vehicles/assign-driver/', views.assign_driver_to_vehicle, name='assign_driver_to_vehicle'),
    path('vehicles/unassign-driver/', views.unassign_driver_from_vehicle, name='unassign_driver_from_vehicle'),
    
    # Géolocalisation temps réel
    path('vehicles/update-position/', views.update_vehicle_position, name='update_vehicle_position'),
    path('vehicles/positions/', views.get_vehicle_positions, name='get_vehicle_positions'),
    
    # Routes avec paramètres UUID (APRÈS les routes spécifiques)
    path('vehicles/<uuid:pk>/', views.VehicleDetailView.as_view(), name='vehicle_detail'),
    
    # Nouvelle gestion d'attribution véhicules-conducteurs
    path('vehicles/<uuid:vehicle_id>/assign-driver/', views.VehicleAssignDriverView.as_view(), name='vehicle_assign_driver'),
    path('vehicles/<uuid:vehicle_id>/unassign-driver/', views.VehicleUnassignDriverView.as_view(), name='vehicle_unassign_driver'),
    path('vehicles/<uuid:vehicle_id>/assignment-history/', views.VehicleAssignmentHistoryView.as_view(), name='vehicle_assignment_history'),
    path('vehicles/<uuid:vehicle_id>/available-drivers/', views.AvailableDriversForVehicleView.as_view(), name='vehicle_available_drivers'),
    
    # APIs générales
    path('available-drivers/', views.get_available_drivers, name='available_drivers'),
    path('available-vehicles/', views.get_available_vehicles, name='available_vehicles'),
    
    # Voyage conducteur
    path('driver/current-trip/', views.get_driver_current_trip, name='get_driver_current_trip'),
    path('driver/trips/', views.get_driver_trips, name='get_driver_trips'),
    
    # Trips - Liste et création
    path('', views.TripListCreateView.as_view(), name='trip_list_create'),
    path('<uuid:pk>/', views.TripDetailView.as_view(), name='trip_detail'),
    
    # Trip actions - Nouvelles vues pour le cycle de vie complet
    path('<uuid:trip_id>/start/', views.TripStartView.as_view(), name='trip_start'),
    path('<uuid:trip_id>/complete/', views.TripCompleteView.as_view(), name='trip_complete'),
    path('<uuid:trip_id>/cancel/', views.TripCancelView.as_view(), name='trip_cancel'),
    path('<uuid:trip_id>/update-position/', views.TripUpdatePositionView.as_view(), name='trip_update_position'),
    
    # Trip actions avec navigation GPS complète
    path('<uuid:trip_id>/start-navigation/', views.start_trip_with_navigation, name='start_trip_navigation'),
    path('<uuid:trip_id>/update-navigation/', views.update_navigation_position, name='update_navigation_position'),
    
    # Trip planning and routing
    path('plan/', views.TripPlanningView.as_view(), name='trip_planning'),
    path('route/calculate/', views.RouteCalculationView.as_view(), name='route_calculation'),
    
    # Rest stops
    path('<uuid:trip_id>/stops/', views.RestStopListCreateView.as_view(), name='rest_stop_list_create'),
    path('stops/<uuid:pk>/', views.RestStopDetailView.as_view(), name='rest_stop_detail'),
    
    # Statistics
    path('statistics/', views.trip_statistics, name='trip_statistics'),
    
    # Trip tracking endpoints
    path('<uuid:trip_id>/start-tracking/', views.start_trip_tracking, name='start_trip_tracking'),
    path('<uuid:trip_id>/tracking-status/', views.get_trip_tracking_status, name='get_trip_tracking_status'),
    
    # Compatibilité avec anciennes routes (pour éviter les erreurs)
    path('<uuid:trip_id>/start-old/', views.start_trip, name='start_trip_old'),
    path('<uuid:trip_id>/complete-old/', views.complete_trip, name='complete_trip_old'),
    
    # ============================================================
    # ROUTES POUR LES SEGMENTS DE VOYAGE (TripSegment) - ELD CONTINU
    # ============================================================
    
    # Liste et création de segments pour un voyage
    path('<uuid:trip_id>/segments/', views.TripSegmentListCreateView.as_view(), name='trip_segment_list_create'),
    
    # Détails d'un segment spécifique
    path('segments/<uuid:pk>/', views.TripSegmentDetailView.as_view(), name='trip_segment_detail'),
    
    # Actions sur les segments
    path('<uuid:trip_id>/segments/start/', views.start_trip_segment, name='start_trip_segment'),
    path('segments/<uuid:segment_id>/end/', views.end_trip_segment, name='end_trip_segment'),
    path('<uuid:trip_id>/segments/switch/', views.switch_segment_type, name='switch_segment_type'),
    
    # Récupération d'informations sur les segments
    path('<uuid:trip_id>/segments/active/', views.get_active_segment, name='get_active_segment'),
    path('<uuid:trip_id>/segments/summary/', views.trip_segment_summary, name='trip_segment_summary'),
]