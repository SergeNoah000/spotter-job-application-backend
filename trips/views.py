from django.shortcuts import render
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from datetime import datetime, timedelta
from django.db import models
import requests
import json
import math
from .models import Vehicle, Trip, RestStop, TripWaypoint
from .serializers import (
    VehicleSerializer, TripSerializer, TripCreateSerializer, TripUpdateSerializer,
    RestStopSerializer, TripWaypointSerializer, TripPlanningSerializer,
    RouteCalculationSerializer
)
from .services import HOSCalculator, NominatimService
from accounts.views import IsFleetManagerOrAdmin
from accounts.models import User
from accounts.serializers import UserSerializer
import logging

logger = logging.getLogger(__name__)

class VehicleListCreateView(generics.ListCreateAPIView):
    """Vue pour lister et créer les véhicules"""
    
    queryset = Vehicle.objects.select_related('company')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_admin():
            return Vehicle.objects.select_related('company').all()
        else:
            return Vehicle.objects.filter(company=user.company)
    
    def perform_create(self, serializer):
        if self.request.user.is_admin():
            serializer.save()
        else:
            serializer.save(company=self.request.user.company)

class VehicleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Vue pour consulter, modifier et supprimer un véhicule"""
    
    queryset = Vehicle.objects.select_related('company')
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        
        if user.is_admin() or obj.company == user.company:
            return obj
        else:
            raise permissions.PermissionDenied("Not authorized to access this vehicle")

class TripListCreateView(generics.ListCreateAPIView):
    """Vue pour lister et créer les voyages"""
    
    queryset = Trip.objects.select_related('driver', 'vehicle').prefetch_related('rest_stops', 'waypoints')
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return TripCreateSerializer
        return TripSerializer
    
    def get_queryset(self):
        user = self.request.user
        queryset = Trip.objects.select_related('driver', 'vehicle').prefetch_related('rest_stops', 'waypoints')
        
        if user.is_admin():
            return queryset
        elif user.is_fleet_manager():
            return queryset.filter(driver__company=user.company)
        else:
            return queryset.filter(driver=user)
    
    def perform_create(self, serializer):
        user = self.request.user
        
        # Vérifier les permissions
        if not user.can_create_trips:
            raise permissions.PermissionDenied("Not authorized to create trips")
        
        # Pour les conducteurs, ils ne peuvent créer que leurs propres voyages
        print(user) 
        if user.is_driver():
            serializer.save(driver=user)
        else:
            serializer.save()

class TripDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Vue pour consulter, modifier et supprimer un voyage"""
    
    queryset = Trip.objects.select_related('driver', 'vehicle').prefetch_related('rest_stops', 'waypoints')
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return TripUpdateSerializer
        return TripSerializer
    
    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        
        if (user.is_admin() or 
            (user.is_fleet_manager() and obj.driver.company == user.company) or
            obj.driver == user):
            return obj
        else:
            raise permissions.PermissionDenied("Not authorized to access this trip")

class TripPlanningView(APIView):
    """Vue pour la planification automatique de voyages avec calculs HOS"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = TripPlanningSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Utiliser le HOSCalculator pour planifier le voyage
                calculator = HOSCalculator(serializer.validated_data)
                trip_schedule = calculator.calculate_trip_schedule()
                
                return Response({
                    'success': True,
                    'trip_schedule': trip_schedule,
                    'message': 'Trip planning completed successfully'
                })
                
            except ValueError as e:
                return Response({
                    'success': False,
                    'error': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.error(f"Trip planning error: {str(e)}")
                return Response({
                    'success': False,
                    'error': 'Internal error during trip planning'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RouteCalculationView(APIView):
    """Vue pour le calcul d'itinéraires optimisés"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = RouteCalculationSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                waypoints = serializer.validated_data['waypoints']
                
                # Créer des données temporaires pour le calculateur
                temp_trip_data = {
                    'current_location': 'Start',
                    'pickup_location': 'Waypoint 1',
                    'dropoff_location': 'End',
                    'current_cycle_hours': 0,
                    'planned_start_time': datetime.now().isoformat()
                }
                
                calculator = HOSCalculator(temp_trip_data)
                route_data = calculator.get_route_from_api([
                    f"{wp['lat']},{wp['lng']}" for wp in waypoints
                ])
                
                return Response({
                    'success': True,
                    'route_data': route_data
                })
                
            except Exception as e:
                logger.error(f"Route calculation error: {str(e)}")
                return Response({
                    'success': False,
                    'error': 'Error calculating route'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RestStopListCreateView(generics.ListCreateAPIView):
    """Vue pour lister et créer les arrêts de repos"""
    
    serializer_class = RestStopSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        trip_id = self.kwargs.get('trip_id')
        return RestStop.objects.filter(trip_id=trip_id).order_by('planned_start_time')
    
    def perform_create(self, serializer):
        trip_id = self.kwargs.get('trip_id')
        try:
            trip = Trip.objects.get(id=trip_id)
            
            # Vérifier les permissions
            user = self.request.user
            if not (user.is_admin() or 
                   (user.is_fleet_manager() and trip.driver.company == user.company) or
                   trip.driver == user):
                raise permissions.PermissionDenied("Not authorized to modify this trip")
            
            serializer.save(trip=trip)
            
        except Trip.DoesNotExist:
            raise generics.Http404("Trip not found")

class RestStopDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Vue pour consulter, modifier et supprimer un arrêt de repos"""
    
    queryset = RestStop.objects.all()
    serializer_class = RestStopSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        
        if (user.is_admin() or 
            (user.is_fleet_manager() and obj.trip.driver.company == user.company) or
            obj.trip.driver == user):
            return obj
        else:
            raise permissions.PermissionDenied("Not authorized to access this rest stop")

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_locations(request):
    """API pour l'autocomplétion des lieux avec Nominatim"""
    try:
        query = request.GET.get('q', '').strip()
        if len(query) < 3:
            return Response({
                'suggestions': [],
                'message': 'Veuillez saisir au moins 3 caractères'
            })
        
        nominatim_service = NominatimService()
        suggestions = nominatim_service.search_address(query, limit=8)
        
        return Response({
            'suggestions': suggestions,
            'count': len(suggestions)
        })
        
    except Exception as e:
        logger.error(f"Error in location search: {str(e)}")
        return Response({
            'error': 'Erreur lors de la recherche d\'adresses',
            'suggestions': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def calculate_route_with_navigation(request):
    """Calculer un itinéraire complet avec données de navigation GPS"""
    try:
        origin = request.data.get('origin')
        destination = request.data.get('destination')
        waypoints = request.data.get('waypoints', [])
        
        if not origin or not destination:
            return Response({
                'error': 'Origin et destination sont requis'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        nominatim_service = NominatimService()
        
        # Calculer l'itinéraire avec OpenRouteService ou équivalent
        route_data = nominatim_service.calculate_route(origin, destination, waypoints)
        
        if not route_data:
            return Response({
                'error': 'Impossible de calculer l\'itinéraire'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'route': route_data,
            'navigation': {
                'total_distance_km': route_data.get('distance_km', 0),
                'total_duration_minutes': route_data.get('duration_minutes', 0),
                'polyline': route_data.get('polyline', ''),
                'turn_by_turn': route_data.get('instructions', []),
                'bbox': route_data.get('bbox', [])
            }
        })
        
    except Exception as e:
        logger.error(f"Error calculating route: {str(e)}")
        return Response({
            'error': 'Erreur lors du calcul de l\'itinéraire'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def get_current_location_address(request):
    """Obtenir l'adresse à partir des coordonnées GPS (géocodage inverse)"""
    try:
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if not latitude or not longitude:
            return Response({
                'error': 'Latitude et longitude requises'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        nominatim_service = NominatimService()
        address_data = nominatim_service.reverse_geocode(float(latitude), float(longitude))
        
        if not address_data:
            return Response({
                'error': 'Impossible de déterminer l\'adresse'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'address': address_data
        })
        
    except Exception as e:
        logger.error(f"Error in reverse geocoding: {str(e)}")
        return Response({
            'error': 'Erreur lors de la géolocalisation inverse'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def start_trip_with_navigation(request, trip_id):
    """Démarrer un voyage avec navigation GPS complète"""
    try:
        user = request.user
        
        if not user.is_driver():
            return Response({
                'error': 'Seuls les conducteurs peuvent démarrer la navigation'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            trip = Trip.objects.get(id=trip_id, driver=user)
        except Trip.DoesNotExist:
            return Response({
                'error': 'Voyage non trouvé ou non assigné'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if trip.status != 'PLANNED':
            return Response({
                'error': f'Impossible de démarrer le voyage avec le statut: {trip.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Récupérer la position actuelle du conducteur
        current_latitude = request.data.get('current_latitude')
        current_longitude = request.data.get('current_longitude')
        
        if not current_latitude or not current_longitude:
            return Response({
                'error': 'Position actuelle requise pour la navigation'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            lat = float(current_latitude)
            lng = float(current_longitude)
        except (ValueError, TypeError):
            return Response({
                'error': 'Coordonnées GPS invalides'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculer l'itinéraire complet
        nominatim_service = NominatimService()
        
        # Géocoder la destination si pas encore fait
        if not hasattr(trip, 'destination_lat') or not trip.destination_lat:
            dest_coords = nominatim_service.geocode_address(trip.destination)
            if dest_coords:
                trip.destination_lat = dest_coords['lat']
                trip.destination_lng = dest_coords['lng']
        
        # Calculer la route
        origin = {'lat': lat, 'lng': lng}
        destination = {
            'lat': trip.destination_lat or 0,
            'lng': trip.destination_lng or 0,
            'address': trip.destination
        }
        
        route_data = nominatim_service.calculate_route(origin, destination)
        if not route_data:
            return Response({
                'error': 'Impossible de calculer l\'itinéraire de navigation'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Démarrer le voyage avec navigation
        trip.status = 'IN_PROGRESS'
        trip.start_time = datetime.now()
        trip.current_lat = lat
        trip.current_lng = lng
        trip.route_data = json.dumps(route_data)
        trip.estimated_distance_km = route_data.get('distance_km', 0)
        trip.estimated_duration_minutes = route_data.get('duration_minutes', 0)
        trip.save()
        
        # Mettre à jour le véhicule
        if hasattr(user, 'assigned_vehicle') and user.assigned_vehicle:
            vehicle = user.assigned_vehicle
            vehicle.current_latitude = lat
            vehicle.current_longitude = lng
            vehicle.operational_status = 'IN_USE'
            vehicle.last_location_update = datetime.now()
            vehicle.save()
        
        return Response({
            'success': True,
            'message': 'Navigation démarrée avec succès',
            'trip': TripSerializer(trip).data,
            'navigation': {
                'status': 'ACTIVE',
                'current_position': {'lat': lat, 'lng': lng},
                'destination': destination,
                'route': route_data
            },
            'redirect_url': f'/tracking/{trip_id}'
        })
        
    except Exception as e:
        logger.error(f"Erreur lors du démarrage de la navigation: {str(e)}")
        return Response({
            'error': 'Erreur lors du démarrage de la navigation'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_navigation_position(request, trip_id):
    """Mettre à jour la position GPS pendant la navigation"""
    try:
        user = request.user
        
        if not user.is_driver():
            return Response({
                'error': 'Seuls les conducteurs peuvent mettre à jour la position'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            trip = Trip.objects.get(id=trip_id, driver=user, status='IN_PROGRESS')
        except Trip.DoesNotExist:
            return Response({
                'error': 'Voyage actif non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        bearing = request.data.get('bearing', 0)
        speed = request.data.get('speed', 0)
        
        if not latitude or not longitude:
            return Response({
                'error': 'Latitude et longitude requises'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            lat = float(latitude)
            lng = float(longitude)
            bearing = float(bearing) if bearing else 0
            speed = float(speed) if speed else 0
        except (ValueError, TypeError):
            return Response({
                'error': 'Valeurs de coordonnées invalides'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculer la distance restante vers la destination
        nominatim_service = NominatimService()
        remaining_distance = 0
        
        if hasattr(trip, 'destination_lat') and trip.destination_lat:
            remaining_distance = nominatim_service.calculate_distance(
                lat, lng, trip.destination_lat, trip.destination_lng
            )
        
        # Mettre à jour la position
        trip.current_lat = lat
        trip.current_lng = lng
        trip.save()
        
        # Mettre à jour le véhicule
        if hasattr(user, 'assigned_vehicle') and user.assigned_vehicle:
            vehicle = user.assigned_vehicle
            vehicle.current_latitude = lat
            vehicle.current_longitude = lng
            vehicle.last_location_update = datetime.now()
            vehicle.save()
        
        # Vérifier si arrivé à destination (moins de 100m)
        is_arrived = remaining_distance < 0.1  # 100 mètres
        
        response_data = {
            'success': True,
            'position_updated': True,
            'current_position': {
                'lat': lat,
                'lng': lng,
                'bearing': bearing,
                'speed_kmh': speed,
                'timestamp': datetime.now().isoformat()
            },
            'navigation': {
                'remaining_distance_km': round(remaining_distance, 2),
                'is_arrived': is_arrived,
                'estimated_arrival': trip.estimated_duration_minutes
            }
        }
        
        # Auto-complétion du voyage si arrivé
        if is_arrived and trip.status == 'IN_PROGRESS':
            trip.status = 'COMPLETED'
            trip.end_time = datetime.now()
            trip.actual_distance_km = trip.estimated_distance_km
            trip.save()
            
            response_data['trip_completed'] = True
            response_data['message'] = 'Voyage terminé automatiquement - Arrivé à destination'
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de position: {str(e)}")
        return Response({
            'error': 'Erreur lors de la mise à jour de la position'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """Statistiques du tableau de bord"""
    try:
        user = request.user
        
        # Filtrer selon les permissions
        if user.is_admin():
            vehicles = Vehicle.objects.all()
            trips = Trip.objects.all()
        elif user.is_fleet_manager():
            vehicles = Vehicle.objects.filter(company=user.company)
            trips = Trip.objects.filter(driver__company=user.company)
        else:
            vehicles = Vehicle.objects.filter(assigned_driver=user)
            trips = Trip.objects.filter(driver=user)
        
        # Calculer les statistiques
        stats = {
            'total_vehicles': vehicles.count(),
            'active_vehicles': vehicles.filter(operational_status='IN_USE').count(),
            'available_vehicles': vehicles.filter(operational_status='AVAILABLE').count(),
            'maintenance_vehicles': vehicles.filter(operational_status='MAINTENANCE').count(),
            
            'total_trips': trips.count(),
            'active_trips': trips.filter(status='IN_PROGRESS').count(),
            'completed_trips': trips.filter(status='COMPLETED').count(),
            'planned_trips': trips.filter(status='PLANNED').count(),
            
            'recent_trips': TripSerializer(trips.order_by('-created_at')[:5], many=True).data
        }
        
        return Response(stats)
        
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération des statistiques'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def hos_status(request):
    """Statut HOS du conducteur"""
    try:
        user = request.user
        
        if not user.is_driver():
            return Response({
                'error': 'Seuls les conducteurs ont un statut HOS'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Calculer le statut HOS actuel
        hos_data = {
            'driver_id': user.id,
            'current_status': 'off_duty',
            'drive_time_used': 0,
            'duty_time_used': 0,
            'cycle_time_used': 0,
            'remaining_drive_time': 11 * 60,  # 11 heures en minutes
            'remaining_duty_time': 14 * 60,   # 14 heures en minutes
            'last_break': None,
            'violations': []
        }
        
        return Response(hos_data)
        
    except Exception as e:
        logger.error(f"Error getting HOS status: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération du statut HOS'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_dashboard_data(request):
    """Données complètes du tableau de bord"""
    try:
        stats_response = dashboard_stats(request)
        hos_response = hos_status(request) if request.user.is_driver() else None
        
        dashboard_data = {
            'stats': stats_response.data,
            'hos_status': hos_response.data if hos_response and hos_response.status_code == 200 else None,
            'timestamp': datetime.now().isoformat()
        }
        
        return Response(dashboard_data)
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération des données du tableau de bord'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def assign_driver_to_vehicle(request):
    """Assigner un conducteur à un véhicule"""
    try:
        vehicle_id = request.data.get('vehicle_id')
        driver_id = request.data.get('driver_id')
        
        if not vehicle_id or not driver_id:
            return Response({
                'error': 'vehicle_id et driver_id sont requis'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            vehicle = Vehicle.objects.get(id=vehicle_id)
            driver = User.objects.get(id=driver_id)
        except (Vehicle.DoesNotExist, User.DoesNotExist):
            return Response({
                'error': 'Véhicule ou conducteur non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Vérifier les permissions
        user = request.user
        if not (user.is_admin() or (user.is_fleet_manager() and vehicle.company == user.company)):
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Désassigner le véhicule précédent du conducteur
        if hasattr(driver, 'assigned_vehicle') and driver.assigned_vehicle:
            old_vehicle = driver.assigned_vehicle
            old_vehicle.assigned_driver = None
            old_vehicle.save()
        
        # Désassigner l'ancien conducteur du véhicule
        if vehicle.assigned_driver:
            old_driver = vehicle.assigned_driver
            if hasattr(old_driver, 'assigned_vehicle'):
                old_driver.assigned_vehicle = None
                old_driver.save()
        
        # Nouvelle assignation
        vehicle.assigned_driver = driver
        vehicle.save()
        
        return Response({
            'success': True,
            'message': f'Conducteur {driver.get_full_name()} assigné au véhicule {vehicle.vehicle_number}',
            'vehicle': VehicleSerializer(vehicle).data
        })
        
    except Exception as e:
        logger.error(f"Error assigning driver to vehicle: {str(e)}")
        return Response({
            'error': 'Erreur lors de l\'assignation'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def unassign_driver_from_vehicle(request):
    """Désassigner un conducteur d'un véhicule"""
    try:
        vehicle_id = request.data.get('vehicle_id')
        
        if not vehicle_id:
            return Response({
                'error': 'vehicle_id requis'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            vehicle = Vehicle.objects.get(id=vehicle_id)
        except Vehicle.DoesNotExist:
            return Response({
                'error': 'Véhicule non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Vérifier les permissions
        user = request.user
        if not (user.is_admin() or (user.is_fleet_manager() and vehicle.company == user.company)):
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if not vehicle.assigned_driver:
            return Response({
                'error': 'Aucun conducteur assigné à ce véhicule'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        driver = vehicle.assigned_driver
        
        # Désassignation
        vehicle.assigned_driver = None
        vehicle.save()
        
        return Response({
            'success': True,
            'message': f'Conducteur {driver.get_full_name()} désassigné du véhicule {vehicle.vehicle_number}',
            'vehicle': VehicleSerializer(vehicle).data
        })
        
    except Exception as e:
        logger.error(f"Error unassigning driver from vehicle: {str(e)}")
        return Response({
            'error': 'Erreur lors de la désassignation'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_available_drivers(request):
    """Récupérer les conducteurs disponibles"""
    try:
        user = request.user
        
        if user.is_admin():
            drivers = User.objects.filter(user_type='DRIVER', assigned_vehicle__isnull=True)
        elif user.is_fleet_manager():
            drivers = User.objects.filter(
                user_type='DRIVER', 
                company=user.company,
                assigned_vehicle__isnull=True
            )
        else:
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = UserSerializer(drivers, many=True)
        return Response({
            'drivers': serializer.data,
            'count': drivers.count()
        })
        
    except Exception as e:
        logger.error(f"Error getting available drivers: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération des conducteurs disponibles'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_available_vehicles(request):
    """Récupérer les véhicules disponibles"""
    try:
        user = request.user
        
        if user.is_admin():
            vehicles = Vehicle.objects.filter(assigned_driver__isnull=True)
        elif user.is_fleet_manager():
            vehicles = Vehicle.objects.filter(
                company=user.company,
                assigned_driver__isnull=True
            )
        else:
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = VehicleSerializer(vehicles, many=True)
        return Response({
            'vehicles': serializer.data,
            'count': vehicles.count()
        })
        
    except Exception as e:
        logger.error(f"Error getting available vehicles: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération des véhicules disponibles'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_vehicle_position(request):
    """Mettre à jour la position d'un véhicule"""
    try:
        user = request.user
        
        if not user.is_driver():
            return Response({
                'error': 'Seuls les conducteurs peuvent mettre à jour la position'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if not hasattr(user, 'assigned_vehicle') or not user.assigned_vehicle:
            return Response({
                'error': 'Aucun véhicule assigné'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if not latitude or not longitude:
            return Response({
                'error': 'Latitude et longitude requises'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            lat = float(latitude)
            lng = float(longitude)
        except (ValueError, TypeError):
            return Response({
                'error': 'Valeurs de coordonnées invalides'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        vehicle = user.assigned_vehicle
        vehicle.current_latitude = lat
        vehicle.current_longitude = lng
        vehicle.last_location_update = datetime.now()
        vehicle.save()
        
        return Response({
            'success': True,
            'message': 'Position mise à jour',
            'position': {
                'latitude': vehicle.current_latitude,
                'longitude': vehicle.current_longitude,
                'timestamp': vehicle.last_location_update.isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating vehicle position: {str(e)}")
        return Response({
            'error': 'Erreur lors de la mise à jour de la position'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_vehicle_positions(request):
    """Récupérer les positions de tous les véhicules"""
    try:
        user = request.user
        
        if user.is_admin():
            vehicles = Vehicle.objects.filter(
                current_latitude__isnull=False,
                current_longitude__isnull=False
            )
        elif user.is_fleet_manager():
            vehicles = Vehicle.objects.filter(
                company=user.company,
                current_latitude__isnull=False,
                current_longitude__isnull=False
            )
        else:
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        positions = []
        for vehicle in vehicles:
            positions.append({
                'vehicle_id': vehicle.id,
                'vehicle_number': vehicle.vehicle_number,
                'latitude': vehicle.current_latitude,
                'longitude': vehicle.current_longitude,
                'last_update': vehicle.last_location_update.isoformat() if vehicle.last_location_update else None,
                'operational_status': vehicle.operational_status,
                'driver': vehicle.assigned_driver.get_full_name() if vehicle.assigned_driver else None
            })
        
        return Response({
            'positions': positions,
            'count': len(positions)
        })
        
    except Exception as e:
        logger.error(f"Error getting vehicle positions: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération des positions'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_driver_current_trip(request):
    """Récupérer le voyage actuel du conducteur"""
    try:
        user = request.user
        
        if not user.is_driver():
            return Response({
                'error': 'Seuls les conducteurs ont des voyages'
            }, status=status.HTTP_403_FORBIDDEN)
        
        current_trip = Trip.objects.filter(
            driver=user,
            status='IN_PROGRESS'
        ).first()
        
        if current_trip:
            serializer = TripSerializer(current_trip)
            return Response({
                'has_current_trip': True,
                'trip': serializer.data
            })
        else:
            return Response({
                'has_current_trip': False,
                'trip': None
            })
        
    except Exception as e:
        logger.error(f"Error getting driver current trip: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération du voyage actuel'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def start_trip(request, trip_id):
    """Démarrer un voyage"""
    try:
        user = request.user
        
        try:
            trip = Trip.objects.get(id=trip_id)
        except Trip.DoesNotExist:
            return Response({
                'error': 'Voyage non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Vérifier les permissions
        if not (user.is_admin() or trip.driver == user or 
                (user.is_fleet_manager() and trip.driver.company == user.company)):
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if trip.status != 'PLANNED':
            return Response({
                'error': f'Impossible de démarrer le voyage avec le statut: {trip.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        trip.status = 'IN_PROGRESS'
        trip.start_time = datetime.now()
        trip.save()
        
        serializer = TripSerializer(trip)
        return Response({
            'success': True,
            'message': 'Voyage démarré avec succès',
            'trip': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error starting trip: {str(e)}")
        return Response({
            'error': 'Erreur lors du démarrage du voyage'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def complete_trip(request, trip_id):
    """Terminer un voyage"""
    try:
        user = request.user
        
        try:
            trip = Trip.objects.get(id=trip_id)
        except Trip.DoesNotExist:
            return Response({
                'error': 'Voyage non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Vérifier les permissions
        if not (user.is_admin() or trip.driver == user or 
                (user.is_fleet_manager() and trip.driver.company == user.company)):
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if trip.status != 'IN_PROGRESS':
            return Response({
                'error': f'Impossible de terminer le voyage avec le statut: {trip.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        trip.status = 'COMPLETED'
        trip.end_time = datetime.now()
        trip.save()
        
        # Mettre à jour le véhicule
        if trip.vehicle and trip.vehicle.assigned_driver:
            vehicle = trip.vehicle
            vehicle.operational_status = 'AVAILABLE'
            vehicle.save()
        
        serializer = TripSerializer(trip)
        return Response({
            'success': True,
            'message': 'Voyage terminé avec succès',
            'trip': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error completing trip: {str(e)}")
        return Response({
            'error': 'Erreur lors de la finalisation du voyage'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def trip_statistics(request):
    """Statistiques des voyages"""
    try:
        user = request.user
        
        if user.is_admin():
            trips = Trip.objects.all()
        elif user.is_fleet_manager():
            trips = Trip.objects.filter(driver__company=user.company)
        else:
            trips = Trip.objects.filter(driver=user)
        
        # Calculer les statistiques
        stats = {
            'total_trips': trips.count(),
            'completed_trips': trips.filter(status='COMPLETED').count(),
            'in_progress_trips': trips.filter(status='IN_PROGRESS').count(),
            'planned_trips': trips.filter(status='PLANNED').count(),
            'cancelled_trips': trips.filter(status='CANCELLED').count(),
        }
        
        # Ajouter des statistiques par période
        today = datetime.now().date()
        stats['today'] = trips.filter(created_at__date=today).count()
        stats['this_week'] = trips.filter(created_at__date__gte=today - timedelta(days=7)).count()
        stats['this_month'] = trips.filter(created_at__date__gte=today.replace(day=1)).count()
        
        return Response(stats)
        
    except Exception as e:
        logger.error(f"Error getting trip statistics: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération des statistiques'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def start_trip_tracking(request, trip_id):
    """Démarrer le suivi GPS d'un voyage"""
    try:
        user = request.user
        
        if not user.is_driver():
            return Response({
                'error': 'Seuls les conducteurs peuvent démarrer le suivi'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            trip = Trip.objects.get(id=trip_id, driver=user)
        except Trip.DoesNotExist:
            return Response({
                'error': 'Voyage non trouvé ou non assigné'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if trip.status != 'PLANNED':
            return Response({
                'error': f'Impossible de démarrer le suivi avec le statut: {trip.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Démarrer le voyage et le suivi
        trip.status = 'IN_PROGRESS'
        trip.start_time = datetime.now()
        trip.save()
        
        return Response({
            'success': True,
            'message': 'Suivi GPS démarré',
            'trip_id': str(trip.id),
            'status': trip.status
        })
        
    except Exception as e:
        logger.error(f"Error starting trip tracking: {str(e)}")
        return Response({
            'error': 'Erreur lors du démarrage du suivi'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_trip_tracking_status(request, trip_id):
    """Récupérer le statut de suivi d'un voyage"""
    try:
        user = request.user
        
        try:
            trip = Trip.objects.get(id=trip_id)
        except Trip.DoesNotExist:
            return Response({
                'error': 'Voyage non trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Vérifier les permissions
        if not (user.is_admin() or trip.driver == user or 
                (user.is_fleet_manager() and trip.driver.company == user.company)):
            return Response({
                'error': 'Permission refusée'
            }, status=status.HTTP_403_FORBIDDEN)
        
        tracking_status = {
            'trip_id': str(trip.id),
            'status': trip.status,
            'is_active': trip.status == 'IN_PROGRESS',
            'current_position': {
                'latitude': getattr(trip, 'current_lat', None),
                'longitude': getattr(trip, 'current_lng', None)
            } if hasattr(trip, 'current_lat') and trip.current_lat and trip.current_lng else None,
            'start_time': trip.start_time.isoformat() if trip.start_time else None,
            'driver': trip.driver.get_full_name(),
            'vehicle': trip.vehicle.vehicle_number if trip.vehicle else None
        }
        
        return Response(tracking_status)
        
    except Exception as e:
        logger.error(f"Error getting trip tracking status: {str(e)}")
        return Response({
            'error': 'Erreur lors de la récupération du statut de suivi'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
