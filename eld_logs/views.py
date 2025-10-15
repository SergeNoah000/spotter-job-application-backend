from django.shortcuts import render
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from datetime import datetime, timedelta
from .models import ELDLog, HOSViolation, ELDExport, DutyStatusEntry
from .serializers import ELDLogSerializer, ELDLogCreateSerializer
from .services import HOSService
import logging
from trips.models import Trip

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

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def change_duty_status(request):
    """
    Changer le statut de service HOS du conducteur
    
    Body params:
        - status: OFF_DUTY, SLEEPER_BERTH, DRIVING, ON_DUTY_NOT_DRIVING
        - location: Localisation textuelle (optionnel)
        - latitude: Latitude GPS (optionnel)
        - longitude: Longitude GPS (optionnel)
        - remarks: Remarques (optionnel)
    """
    user = request.user
    
    if not user.is_driver():
        return Response({
            'error': 'Only drivers can change duty status'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        new_status = request.data.get('status', '').upper()
        location = request.data.get('location')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        remarks = request.data.get('remarks', '')
        
        # Valider le statut
        valid_statuses = ['OFF_DUTY', 'SLEEPER_BERTH', 'DRIVING', 'ON_DUTY_NOT_DRIVING']
        if new_status not in valid_statuses:
            return Response({
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Utiliser le service HOS pour changer le statut
        success, message, entry = HOSService.change_duty_status(
            driver=user,
            new_status=new_status,
            location=location,
            latitude=latitude,
            longitude=longitude,
            remarks=remarks
        )
        
        if not success:
            return Response({
                'success': False,
                'warning': message,
                'violation': True
            }, status=status.HTTP_200_OK)
        
        # Récupérer les heures disponibles
        available_hours = HOSService.get_available_hours(user)
        
        return Response({
            'success': True,
            'message': message,
            'entry': {
                'id': str(entry.id),
                'status': entry.status,
                'start_time': entry.start_time.isoformat(),
                'location': entry.location,
                'remarks': entry.remarks
            },
            'available_hours': available_hours
        })
        
    except Exception as e:
        logger.error(f"Error changing duty status: {str(e)}")
        return Response({
            'error': f'An error occurred: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_current_hos_status(request):
    """
    Récupérer le statut HOS actuel et les heures disponibles du conducteur
    """
    user = request.user
    
    if not user.is_driver():
        return Response({
            'error': 'Only drivers can access this endpoint'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # Utiliser le service HOS
        status_info = HOSService.get_driver_current_status(user)
        available_hours = HOSService.get_available_hours(user)
        
        current_status = status_info['current_status']
        eld_log = status_info['eld_log']
        
        return Response({
            'current_status': {
                'status': current_status['status'],
                'start_time': current_status['start_time'].isoformat() if current_status['start_time'] else None,
                'duration_hours': round(current_status['duration_hours'], 2),
                'location': current_status['location'],
                'remarks': current_status['remarks']
            },
            'daily_summary': {
                'date': eld_log.log_date.isoformat(),
                'driving_hours': float(eld_log.driving_hours),
                'on_duty_hours': float(eld_log.total_duty_hours),
                'off_duty_hours': float(eld_log.off_duty_hours),
                'sleeper_berth_hours': float(eld_log.sleeper_berth_hours)
            },
            'available_hours': available_hours,
            'violations': eld_log.has_violations,
            'violation_notes': eld_log.violation_notes if eld_log.has_violations else None
        })
        
    except Exception as e:
        logger.error(f"Error getting HOS status: {str(e)}")
        return Response({
            'error': 'An error occurred while fetching HOS status'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_duty_status_entries(request):
    """
    Récupérer les entrées de statut pour une date donnée
    
    Query params:
        - date: YYYY-MM-DD (optionnel, défaut: aujourd'hui)
    """
    user = request.user
    date_param = request.GET.get('date')
    
    try:
        # Déterminer la date cible
        if date_param:
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        else:
            target_date = datetime.now().date()
        
        # Obtenir le log ELD
        if user.is_driver():
            eld_log = ELDLog.objects.filter(
                driver=user,
                log_date=target_date
            ).first()
        elif user.is_fleet_manager():
            driver_id = request.GET.get('driver_id')
            if not driver_id:
                return Response({
                    'error': 'driver_id parameter required for fleet managers'
                }, status=status.HTTP_400_BAD_REQUEST)
            eld_log = ELDLog.objects.filter(
                driver_id=driver_id,
                driver__company=user.company,
                log_date=target_date
            ).first()
        else:
            return Response({
                'error': 'Access denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if not eld_log:
            return Response({
                'date': target_date.isoformat(),
                'entries': [],
                'summary': {
                    'driving_hours': 0,
                    'on_duty_hours': 0,
                    'off_duty_hours': 0,
                    'sleeper_berth_hours': 0
                }
            })
        
        # Récupérer les entrées de statut
        entries = DutyStatusEntry.objects.filter(
            eld_log=eld_log
        ).order_by('start_time')
        
        entries_data = []
        for entry in entries:
            entries_data.append({
                'id': str(entry.id),
                'status': entry.status,
                'start_time': entry.start_time.isoformat(),
                'end_time': entry.end_time.isoformat() if entry.end_time else None,
                'duration_hours': round(entry.duration_hours, 2) if entry.end_time else None,
                'location': entry.location,
                'latitude': float(entry.latitude) if entry.latitude else None,
                'longitude': float(entry.longitude) if entry.longitude else None,
                'remarks': entry.remarks
            })
        
        return Response({
            'date': target_date.isoformat(),
            'entries': entries_data,
            'summary': {
                'driving_hours': float(eld_log.driving_hours),
                'on_duty_not_driving_hours': float(eld_log.on_duty_not_driving_hours),
                'off_duty_hours': float(eld_log.off_duty_hours),
                'sleeper_berth_hours': float(eld_log.sleeper_berth_hours),
                'total_duty_hours': float(eld_log.total_duty_hours)
            },
            'is_certified': eld_log.is_certified,
            'has_violations': eld_log.has_violations,
            'violation_notes': eld_log.violation_notes
        })
        
    except ValueError:
        return Response({
            'error': 'Invalid date format. Use YYYY-MM-DD'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error getting duty status entries: {str(e)}")
        return Response({
            'error': 'An error occurred while fetching entries'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def certify_daily_log(request):
    """
    Certifier le journal ELD quotidien avec signature électronique
    
    Body params:
        - date: YYYY-MM-DD
        - signature: Données de signature (optionnel)
    """
    user = request.user
    
    if not user.is_driver():
        return Response({
            'error': 'Only drivers can certify logs'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        date_str = request.data.get('date')
        signature_data = request.data.get('signature', '')
        
        if not date_str:
            return Response({
                'error': 'date parameter is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Obtenir le log ELD
        eld_log = ELDLog.objects.filter(
            driver=user,
            log_date=log_date
        ).first()
        
        if not eld_log:
            return Response({
                'error': 'No log found for this date'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Certifier le log
        success, message = HOSService.certify_log(eld_log, signature_data)
        
        if not success:
            return Response({
                'error': message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': True,
            'message': message,
            'certified_at': eld_log.certified_at.isoformat()
        })
        
    except ValueError:
        return Response({
            'error': 'Invalid date format. Use YYYY-MM-DD'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error certifying log: {str(e)}")
        return Response({
            'error': 'An error occurred while certifying log'
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
