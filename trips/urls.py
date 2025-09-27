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
    
    # Vehicles
    path('vehicles/', views.VehicleListCreateView.as_view(), name='vehicle_list_create'),
    path('vehicles/<uuid:pk>/', views.VehicleDetailView.as_view(), name='vehicle_detail'),
    
    # Assignation véhicules-conducteurs
    path('vehicles/assign-driver/', views.assign_driver_to_vehicle, name='assign_driver_to_vehicle'),
    path('vehicles/unassign-driver/', views.unassign_driver_from_vehicle, name='unassign_driver_from_vehicle'),
    path('available-drivers/', views.get_available_drivers, name='available_drivers'),
    path('available-vehicles/', views.get_available_vehicles, name='available_vehicles'),
    
    # Géolocalisation temps réel
    path('vehicles/update-position/', views.update_vehicle_position, name='update_vehicle_position'),
    path('vehicles/positions/', views.get_vehicle_positions, name='get_vehicle_positions'),
    
    # Voyage conducteur
    path('driver/current-trip/', views.get_driver_current_trip, name='get_driver_current_trip'),
    
    # Trips
    path('', views.TripListCreateView.as_view(), name='trip_list_create'),
    path('<uuid:pk>/', views.TripDetailView.as_view(), name='trip_detail'),
    
    # Trip actions avec navigation
    path('<uuid:trip_id>/start-navigation/', views.start_trip_with_navigation, name='start_trip_navigation'),
    path('<uuid:trip_id>/update-position/', views.update_navigation_position, name='update_navigation_position'),
    path('<uuid:trip_id>/start/', views.start_trip, name='start_trip'),
    path('<uuid:trip_id>/complete/', views.complete_trip, name='complete_trip'),
    
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
]