from django.shortcuts import render
from rest_framework import generics, status, permissions, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django.utils import timezone
from datetime import datetime, timedelta
from .models import ELDLog, HOSViolation, ELDExport, DutyStatusEntry
from .serializers import ELDLogSerializer, ELDLogCreateSerializer, DutyStatusEntrySerializer, HOSViolationSerializer
import logging
from trips.models import Trip
from django.db.models import Q
from .services import HOSRulesEngine, ELDLogService

logger = logging.getLogger(__name__)

class ELDLogListCreateView(generics.ListCreateAPIView):
    """Vue pour lister et créer les logs ELD"""
    
    serializer_class = ELDLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ELDLogCreateSerializer
        return ELDLogSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_admin():
            return ELDLog.objects.all().order_by('-created_at')
        elif user.is_fleet_manager():
            return ELDLog.objects.filter(
                driver__company=user.company
            ).order_by('-created_at')
        else:
            # Conducteurs voient seulement leurs propres logs
            return ELDLog.objects.filter(driver=user).order_by('-created_at')
    
    def perform_create(self, serializer):
        user = self.request.user
        
        # Pour les conducteurs, assigner automatiquement leur ID et véhicule
        if user.is_driver():
            vehicle = user.assigned_vehicle if user.has_assigned_vehicle else None
            serializer.save(driver=user, vehicle=vehicle)
        else:
            serializer.save()

class ELDLogDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Vue pour consulter, modifier et supprimer un log ELD"""
    
    serializer_class = ELDLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.is_admin():
            return ELDLog.objects.all()
        elif user.is_fleet_manager():
            return ELDLog.objects.filter(driver__company=user.company)
        else:
            return ELDLog.objects.filter(driver=user)

class HOSViolationListView(generics.ListAPIView):
    queryset = HOSViolation.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        return Response({'message': 'HOS Violations endpoint - Coming soon'})

class HOSViolationDetailView(generics.RetrieveAPIView):
    queryset = HOSViolation.objects.all()
    permission_classes = [permissions.IsAuthenticated]

class ELDExportListCreateView(generics.ListCreateAPIView):
    queryset = ELDExport.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request):
        return Response({'message': 'ELD Exports endpoint - Coming soon'})

class ELDExportDetailView(generics.RetrieveAPIView):
    queryset = ELDExport.objects.all()
    permission_classes = [permissions.IsAuthenticated]

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_eld_from_trip(request, trip_id):
    """Générer un journal ELD à partir d'un voyage"""
    try:
        trip = Trip.objects.get(id=trip_id)
        return Response({
            'success': True,
            'message': f'ELD generation for trip {trip_id} - Coming soon'
        })
    except Trip.DoesNotExist:
        return Response({
            'error': 'Trip not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_hos_status_change(request):
    """Créer un changement de statut HOS"""
    
    try:
        user = request.user
        
        if not user.is_driver():
            return Response({
                'error': 'Only drivers can create HOS status changes'
            }, status=status.HTTP_403_FORBIDDEN)
        
        duty_status = request.data.get('duty_status')
        location = request.data.get('location', 'Unknown')
        notes = request.data.get('notes', '')
        
        if not duty_status:
            return Response({
                'error': 'duty_status is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        valid_statuses = ['off_duty', 'sleeper_berth', 'driving', 'on_duty_not_driving']
        duty_status_lower = duty_status.lower()
        
        if duty_status_lower not in valid_statuses:
            return Response({
                'error': f'Invalid duty_status. Must be one of: {valid_statuses}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Créer un nouveau log ELD
        eld_log = ELDLog.objects.create(
            driver=user,
            log_date=datetime.now().date(),
            duty_status=duty_status_lower,
            start_time=datetime.now(),
            location=location,
            notes=notes,
            trip=user.current_trip if hasattr(user, 'current_trip') and user.current_trip else None,
            vehicle=user.assigned_vehicle if user.has_assigned_vehicle else None,
            vehicle_number=user.assigned_vehicle.vehicle_number if user.has_assigned_vehicle else 'N/A'
        )
        
        return Response({
            'success': True,
            'message': 'HOS status change recorded successfully',
            'entry': {
                'id': str(eld_log.id),
                'duty_status': eld_log.duty_status,
                'start_time': eld_log.start_time.isoformat(),
                'location': eld_log.location,
                'notes': eld_log.notes
            }
        })
        
    except Exception as e:
        logger.error(f"Error creating HOS status change: {str(e)}")
        return Response({
            'error': f'An error occurred while recording status change: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_driver_current_hos_status(request):
    """Récupérer le statut HOS actuel du conducteur"""
    
    user = request.user
    
    if not user.is_driver():
        return Response({
            'error': 'Only drivers can access this endpoint'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        from .models import DutyStatusEntry
        
        # Obtenir le log ELD d'aujourd'hui
        today = datetime.now().date()
        eld_log = ELDLog.objects.filter(
            driver=user,
            log_date=today
        ).first()
        
        if eld_log:
            # Récupérer l'entrée de statut actuelle (sans end_time)
            current_entry = DutyStatusEntry.objects.filter(
                eld_log=eld_log,
                end_time__isnull=True
            ).first()
            
            if current_entry:
                duration = datetime.now() - current_entry.start_time
                duration_hours = duration.total_seconds() / 3600
                
                current_status = {
                    'duty_status': current_entry.status,
                    'start_time': current_entry.start_time.isoformat(),
                    'duration_hours': round(duration_hours, 2),
                    'location': current_entry.location,
                    'notes': current_entry.remarks
                }
            else:
                current_status = {
                    'duty_status': 'OFF_DUTY',
                    'start_time': None,
                    'duration_hours': 0,
                    'location': 'Unknown',
                    'notes': ''
                }
            
            return Response({
                'current_status': current_status,
                'daily_hours': {
                    'driving_hours': float(eld_log.driving_hours),
                    'on_duty_hours': float(eld_log.driving_hours + eld_log.on_duty_not_driving_hours),
                    'remaining_driving': eld_log.remaining_drive_time,
                    'remaining_on_duty': eld_log.remaining_duty_time
                },
                'cycle_hours': {
                    'total_hours': float(eld_log.cycle_hours_used),
                    'remaining_hours': float(eld_log.cycle_hours_available)
                },
                'last_updated': datetime.now().isoformat()
            })
        else:
            # Pas de log pour aujourd'hui
            return Response({
                'current_status': {
                    'duty_status': 'OFF_DUTY',
                    'start_time': None,
                    'duration_hours': 0,
                    'location': 'Unknown',
                    'notes': ''
                },
                'daily_hours': {
                    'driving_hours': 0,
                    'on_duty_hours': 0,
                    'remaining_driving': 11,
                    'remaining_on_duty': 14
                },
                'cycle_hours': {
                    'total_hours': 0,
                    'remaining_hours': 70
                },
                'last_updated': datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Error getting driver HOS status: {str(e)}")
        return Response({
            'error': 'An error occurred while fetching HOS status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_driver_daily_logs(request):
    """Récupérer les logs ELD du jour pour le conducteur"""
    
    user = request.user
    date_param = request.GET.get('date')
    
    try:
        # Utiliser la date fournie ou aujourd'hui par défaut
        if date_param:
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        else:
            target_date = datetime.now().date()
        
        if user.is_driver():
            logs = ELDLog.objects.filter(
                driver=user,
                log_date=target_date
            ).order_by('start_time')
        elif user.is_fleet_manager():
            driver_id = request.GET.get('driver_id')
            if driver_id:
                logs = ELDLog.objects.filter(
                    driver_id=driver_id,
                    driver__company=user.company,
                    log_date=target_date
                ).order_by('start_time')
            else:
                return Response({
                    'error': 'driver_id parameter required for fleet managers'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'error': 'Access denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = ELDLogSerializer(logs, many=True)
        
        return Response({
            'date': target_date.isoformat(),
            'logs': serializer.data,
            'count': logs.count()
        })
        
    except ValueError:
        return Response({
            'error': 'Invalid date format. Use YYYY-MM-DD'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error getting daily logs: {str(e)}")
        return Response({
            'error': 'An error occurred while fetching daily logs'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_duty_status(request):
    """
    Changer le statut de service du conducteur de manière continue.
    Le backend détecte automatiquement si l'activité fait partie d'un voyage implicite
    (entre un ramassage et une livraison).
    """
    user = request.user
    
    if not user.is_driver():
        return Response({
            'error': 'Only drivers can change duty status'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        new_status = request.data.get('status')
        location = request.data.get('location', 'Unknown')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        remarks = request.data.get('remarks', '')
        odometer_reading = request.data.get('odometer_reading')
        
        # Validation du statut
        valid_statuses = ['OFF_DUTY', 'SLEEPER_BERTH', 'DRIVING', 'ON_DUTY_NOT_DRIVING']
        if new_status not in valid_statuses:
            return Response({
                'error': f'Invalid status. Must be one of: {valid_statuses}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        today = datetime.now().date()
        now = datetime.now()
        
        # Obtenir ou créer le log ELD d'aujourd'hui
        eld_log, created = ELDLog.objects.get_or_create(
            driver=user,
            log_date=today,
            defaults={
                'vehicle': user.assigned_vehicle if user.has_assigned_vehicle else None,
                'vehicle_number': user.assigned_vehicle.vehicle_number if user.has_assigned_vehicle else 'N/A',
                'trip': None,
                'created_by': user
            }
        )
        
        # Terminer le segment actif s'il existe
        current_entry = DutyStatusEntry.objects.filter(
            eld_log=eld_log,
            end_time__isnull=True
        ).first()
        
        if current_entry:
            current_entry.end_time = now
            current_entry.updated_by = user
            current_entry.save()
        
        # LOGIQUE INTELLIGENTE : Détecter automatiquement le voyage implicite
        # Un voyage implicite existe entre un ramassage (PICKUP_ARRIVED) et une livraison (DELIVERED)
        associated_trip = detect_implicit_trip(user)
        
        # Créer le nouveau segment
        new_entry = DutyStatusEntry.objects.create(
            eld_log=eld_log,
            trip=associated_trip,  # Peut être None si pas de voyage en cours
            start_time=now,
            end_time=None,  # Segment actif
            status=new_status,
            location=location,
            latitude=latitude,
            longitude=longitude,
            remarks=remarks,
            odometer_reading=odometer_reading,
            created_by=user
        )
        
        # Recalculer les totaux
        eld_log.calculate_daily_totals()
        
        from .serializers import DutyStatusEntrySerializer
        
        return Response({
            'success': True,
            'message': 'Duty status changed successfully',
            'entry': DutyStatusEntrySerializer(new_entry).data,
            'daily_hours': {
                'driving_hours': float(eld_log.driving_hours),
                'on_duty_hours': float(eld_log.total_duty_hours),
                'remaining_driving': eld_log.remaining_drive_time,
                'remaining_on_duty': eld_log.remaining_duty_time
            },
            'implicit_trip': {
                'id': str(associated_trip.id) if associated_trip else None,
                'trip_number': associated_trip.trip_number if associated_trip else None,
                'status': associated_trip.status if associated_trip else None
            }
        })
        
    except Exception as e:
        logger.error(f"Error changing duty status: {str(e)}")
        return Response({
            'error': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def detect_implicit_trip(driver):
    """
    Détecte automatiquement si le conducteur est dans un voyage implicite.
    Un voyage implicite existe quand :
    - Le conducteur a fait un ramassage (PICKUP_ARRIVED) 
    - Mais n'a pas encore fait de livraison (DELIVERED)
    
    Returns:
        Trip or None: Le voyage implicite détecté ou None
    """
    # Chercher un voyage avec un ramassage effectué mais pas encore livré
    # Status possibles pendant le voyage : 'AT_PICKUP', 'IN_TRANSIT'
    implicit_trip = Trip.objects.filter(
        driver=driver,
        status__in=['AT_PICKUP', 'IN_TRANSIT'],
        actual_departure__isnull=False,  # Ramassage effectué
        actual_arrival__isnull=True      # Pas encore livré
    ).order_by('-actual_departure').first()
    
    return implicit_trip

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def link_segment_to_trip(request, segment_id):
    """
    Lier manuellement un segment à un voyage.
    Utilisé quand le conducteur veut associer rétroactivement un segment à un voyage.
    """
    user = request.user
    trip_id = request.data.get('trip_id')
    
    try:
        segment = DutyStatusEntry.objects.get(id=segment_id)
        
        # Vérifier les permissions
        if segment.eld_log.driver != user and not user.is_fleet_manager():
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if trip_id:
            trip = Trip.objects.get(id=trip_id)
            
            # Vérifier que le voyage appartient au même conducteur
            if trip.driver != segment.eld_log.driver:
                return Response({
                    'error': 'Trip does not belong to this driver'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            segment.trip = trip
        else:
            segment.trip = None
        
        segment.updated_by = user
        segment.save()
        
        from .serializers import DutyStatusEntrySerializer
        
        return Response({
            'success': True,
            'message': 'Segment linked to trip successfully',
            'segment': DutyStatusEntrySerializer(segment).data
        })
        
    except DutyStatusEntry.DoesNotExist:
        return Response({
            'error': 'Segment not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Trip.DoesNotExist:
        return Response({
            'error': 'Trip not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error linking segment to trip: {str(e)}")
        return Response({
            'error': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_driver_activity(request):
    """
    Récupérer l'activité du conducteur (segments de conduite/repos)
    Indépendant des voyages - affiche tous les segments du conducteur
    Détecte automatiquement le voyage implicite en cours
    """
    user = request.user
    
    if not user.is_driver():
        return Response({
            'error': 'Only drivers can access this endpoint'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # Récupérer tous les segments du conducteur pour aujourd'hui
        today = datetime.now().date()
        
        # Obtenir ou créer le log ELD du jour
        eld_log, created = ELDLog.objects.get_or_create(
            driver=user,
            log_date=today,
            defaults={
                'vehicle': user.assigned_vehicle if user.has_assigned_vehicle else None,
                'vehicle_number': user.assigned_vehicle.vehicle_number if user.has_assigned_vehicle else 'N/A',
                'duty_status': 'off_duty',
                'start_time': datetime.now()
            }
        )
        
        # Récupérer tous les segments du conducteur (avec ou sans voyage)
        segments = DutyStatusEntry.objects.filter(
            eld_log=eld_log
        ).order_by('start_time')
        
        # Sérialiser les segments
        serializer = DutyStatusEntrySerializer(segments, many=True)
        
        # DÉTECTION AUTOMATIQUE DU VOYAGE IMPLICITE
        implicit_trip = detect_implicit_trip(user)
        
        implicit_trip_info = None
        if implicit_trip:
            implicit_trip_info = {
                'id': str(implicit_trip.id),
                'trip_number': implicit_trip.trip_number,
                'origin': implicit_trip.origin,
                'destination': implicit_trip.destination,
                'status': implicit_trip.status,
                'pickup_location': implicit_trip.pickup_location,
                'delivery_location': implicit_trip.delivery_location,
                'actual_departure': implicit_trip.actual_departure.isoformat() if implicit_trip.actual_departure else None,
                'estimated_arrival': implicit_trip.estimated_arrival.isoformat() if implicit_trip.estimated_arrival else None
            }
        
        # Calculer les statistiques HOS
        hos_stats = calculate_hos_statistics(segments)
        
        # Récupérer le statut actuel
        current_segment = segments.filter(end_time__isnull=True).first()
        current_status = None
        if current_segment:
            duration = datetime.now() - current_segment.start_time
            current_status = {
                'status': current_segment.status,
                'start_time': current_segment.start_time.isoformat(),
                'duration_minutes': int(duration.total_seconds() / 60),
                'location': current_segment.location
            }
        
        return Response({
            'success': True,
            'segments': serializer.data,
            'current_status': current_status,
            'implicit_trip': implicit_trip_info,
            'hos_statistics': hos_stats,
            'daily_totals': {
                'driving_hours': float(eld_log.driving_hours),
                'on_duty_hours': float(eld_log.total_duty_hours),
                'remaining_driving': eld_log.remaining_drive_time,
                'remaining_on_duty': eld_log.remaining_duty_time
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching driver activity: {str(e)}")
        return Response({
            'error': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def calculate_hos_statistics(segments):
    """
    Calculer les statistiques HOS à partir des segments
    """
    stats = {
        'driving_time': 0,
        'on_duty_time': 0,
        'off_duty_time': 0,
        'sleeper_berth_time': 0
    }
    
    now = datetime.now()
    
    for segment in segments:
        end_time = segment.end_time if segment.end_time else now
        duration = (end_time - segment.start_time).total_seconds() / 3600  # en heures
        
        if segment.status == 'DRIVING':
            stats['driving_time'] += duration
        elif segment.status == 'ON_DUTY_NOT_DRIVING':
            stats['on_duty_time'] += duration
        elif segment.status == 'OFF_DUTY':
            stats['off_duty_time'] += duration
        elif segment.status == 'SLEEPER_BERTH':
            stats['sleeper_berth_time'] += duration
    
    # Arrondir à 2 décimales
    for key in stats:
        stats[key] = round(stats[key], 2)
    
    return stats

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def add_driver_activity_segment(request):
    """
    Ajouter un segment d'activité pour le conducteur
    Le segment peut être lié ou non à un voyage
    Auto-création de voyage si on démarre un itinéraire vers une livraison
    """
    user = request.user
    
    if not user.is_driver():
        return Response({
            'error': 'Only drivers can create activity segments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        duty_status = request.data.get('status')
        location = request.data.get('location', 'Unknown')
        notes = request.data.get('remarks', '')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if not duty_status:
            return Response({
                'error': 'status is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        valid_statuses = ['OFF_DUTY', 'SLEEPER_BERTH', 'DRIVING', 'ON_DUTY_NOT_DRIVING']
        
        if duty_status not in valid_statuses:
            return Response({
                'error': f'Invalid status. Must be one of: {valid_statuses}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Obtenir ou créer le log ELD du jour
        today = datetime.now().date()
        eld_log, created = ELDLog.objects.get_or_create(
            driver=user,
            log_date=today,
            defaults={
                'vehicle': user.assigned_vehicle if user.has_assigned_vehicle else None,
                'vehicle_number': user.assigned_vehicle.vehicle_number if user.has_assigned_vehicle else 'N/A',
                'duty_status': 'off_duty',
                'start_time': datetime.now()
            }
        )
        
        # Terminer le segment actuel s'il existe
        current_segment = DutyStatusEntry.objects.filter(
            eld_log=eld_log,
            end_time__isnull=True
        ).first()
        
        if current_segment:
            current_segment.end_time = datetime.now()
            current_segment.save()
        
        # Déterminer le voyage lié (si existant)
        trip = None
        if hasattr(user, 'current_trip') and user.current_trip:
            trip = user.current_trip
        
        # Auto-création de voyage si on commence à conduire et qu'il n'y a pas de voyage actif
        # Logique à implémenter selon vos besoins métier
        
        # Créer le nouveau segment
        new_segment = DutyStatusEntry.objects.create(
            eld_log=eld_log,
            status=duty_status,
            start_time=datetime.now(),
            location=location,
            remarks=notes,
            latitude=latitude,
            longitude=longitude,
            trip=trip  # Peut être None
        )
        
        serializer = DutyStatusEntrySerializer(new_segment)
        
        return Response({
            'success': True,
            'message': 'Activity segment created successfully',
            'segment': serializer.data
        })
        
    except Exception as e:
        logger.error(f"Error creating activity segment: {str(e)}")
        return Response({
            'error': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def calculate_hos_statistics(segments):
    """Calculer les statistiques HOS à partir des segments"""
    stats = {
        'drive_time': 0,
        'on_duty_time': 0,
        'off_duty_time': 0,
        'sleeper_time': 0
    }
    
    for segment in segments:
        if segment.end_time:
            duration = (segment.end_time - segment.start_time).total_seconds() / 3600
            
            if segment.status == 'DRIVING':
                stats['drive_time'] += duration
            elif segment.status == 'ON_DUTY_NOT_DRIVING':
                stats['on_duty_time'] += duration
            elif segment.status == 'OFF_DUTY':
                stats['off_duty_time'] += duration
            elif segment.status == 'SLEEPER_BERTH':
                stats['sleeper_time'] += duration
    
    # Arrondir à 2 décimales
    for key in stats:
        stats[key] = round(stats[key], 2)
    
    return stats

class ELDLogViewSet(viewsets.ModelViewSet):
    queryset = ELDLog.objects.all()
    serializer_class = ELDLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def hos_status(self, request):
        """
        Obtient le statut HOS actuel du conducteur
        GET /api/eld-logs/hos_status/
        """
        hos_engine = HOSRulesEngine(request.user)
        hos_status = hos_engine.get_current_hos_status()
        return Response(hos_status)
    
    @action(detail=False, methods=['get'])
    def can_drive(self, request):
        """
        Vérifie si le conducteur peut commencer à conduire
        GET /api/eld-logs/can_drive/
        """
        hos_engine = HOSRulesEngine(request.user)
        can_drive, reason = hos_engine.can_start_driving()
        
        return Response({
            'can_drive': can_drive,
            'reason': reason,
            'timestamp': timezone.now().isoformat()
        })
    
    @action(detail=False, methods=['get'])
    def available_time(self, request):
        """
        Calcule le temps de conduite disponible
        GET /api/eld-logs/available_time/
        """
        hos_engine = HOSRulesEngine(request.user)
        available_time = hos_engine.calculate_available_driving_time()
        
        return Response(available_time)
    
    @action(detail=False, methods=['post'])
    def predict_violations(self, request):
        """
        Prédit les violations pour un temps de conduite planifié
        POST /api/eld-logs/predict_violations/
        Body: { "planned_hours": 5.0 }
        """
        planned_hours = request.data.get('planned_hours', 0)
        
        if not planned_hours or planned_hours <= 0:
            return Response(
                {'error': 'planned_hours requis et doit être > 0'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        hos_engine = HOSRulesEngine(request.user)
        violations = hos_engine.predict_violation(float(planned_hours))
        
        return Response({
            'planned_hours': planned_hours,
            'predicted_violations': violations,
            'has_violations': len(violations) > 0
        })
    
    @action(detail=False, methods=['post'])
    def change_duty_status(self, request):
        """
        Enregistre un changement de statut de service
        POST /api/eld-logs/change_duty_status/
        Body: {
            "status": "DRIVING",
            "location": "123 Main St, City",
            "latitude": 45.5017,
            "longitude": -73.5673,
            "remarks": "Début de trajet"
        }
        """
        required_fields = ['status', 'location']
        missing_fields = [f for f in required_fields if f not in request.data]
        
        if missing_fields:
            return Response(
                {'error': f'Champs requis manquants: {", ".join(missing_fields)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Valider le statut
        valid_statuses = ['OFF_DUTY', 'SLEEPER_BERTH', 'DRIVING', 'ON_DUTY_NOT_DRIVING']
        duty_status = request.data.get('status')
        
        if duty_status not in valid_statuses:
            return Response(
                {'error': f'Statut invalide. Statuts valides: {", ".join(valid_statuses)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Vérifier si le conducteur peut conduire (si statut = DRIVING)
        if duty_status == 'DRIVING':
            hos_engine = HOSRulesEngine(request.user)
            can_drive, reason = hos_engine.can_start_driving()
            
            if not can_drive:
                return Response(
                    {
                        'error': 'Conduite non autorisée',
                        'reason': reason,
                        'can_drive': False
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Enregistrer le changement de statut
        try:
            hos_engine = HOSRulesEngine(request.user)
            entry = hos_engine.record_duty_status_change(
                status=duty_status,
                location=request.data.get('location'),
                latitude=request.data.get('latitude'),
                longitude=request.data.get('longitude'),
                remarks=request.data.get('remarks', '')
            )
            
            serializer = DutyStatusEntrySerializer(entry)
            return Response({
                'message': 'Statut de service enregistré avec succès',
                'entry': serializer.data,
                'hos_status': hos_engine.get_current_hos_status()
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Erreur lors de l\'enregistrement: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def certify(self, request, pk=None):
        """
        Certifie un log ELD
        POST /api/eld-logs/{id}/certify/
        Body: { "signature": "base64_signature_data" }
        """
        eld_log = self.get_object()
        
        # Vérifier que le log appartient au conducteur
        if eld_log.driver != request.user:
            return Response(
                {'error': 'Vous ne pouvez certifier que vos propres logs'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Vérifier que le log n'est pas déjà certifié
        if eld_log.is_certified:
            return Response(
                {'error': 'Ce log est déjà certifié'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        signature_data = request.data.get('signature')
        if not signature_data:
            return Response(
                {'error': 'Signature requise'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Certifier le log
        ELDLogService.certify_log(eld_log, signature_data)
        
        serializer = self.get_serializer(eld_log)
        return Response({
            'message': 'Log certifié avec succès',
            'log': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def weekly_summary(self, request):
        """
        Obtient un résumé hebdomadaire des logs
        GET /api/eld-logs/weekly_summary/
        """
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        logs = ELDLog.objects.filter(
            driver=request.user,
            log_date__gte=week_start,
            log_date__lte=week_end
        ).order_by('log_date')
        
        summary = {
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
            'total_driving_hours': sum(float(log.driving_hours) for log in logs),
            'total_duty_hours': sum(float(log.driving_hours + log.on_duty_not_driving_hours) for log in logs),
            'days_worked': logs.count(),
            'logs': ELDLogSerializer(logs, many=True).data
        }
        
        return Response(summary)
    
    @action(detail=False, methods=['get'])
    def violations(self, request):
        """
        Obtient toutes les violations HOS du conducteur
        GET /api/eld-logs/violations/
        """
        violations = HOSViolation.objects.filter(
            eld_log__driver=request.user
        ).order_by('-detected_at')[:50]  # 50 dernières violations
        
        serializer = HOSViolationSerializer(violations, many=True)
        return Response({
            'count': violations.count(),
            'violations': serializer.data
        })
