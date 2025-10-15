"""
Service pour gérer les calculs et validations HOS (Hours of Service)
"""
from datetime import datetime, timedelta
from django.utils import timezone
from .models import ELDLog, DutyStatusEntry, HOSViolation
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class HOSService:
    """Service pour les calculs et validations Hours of Service"""
    
    # Limites HOS selon règlements FMCSA
    MAX_DRIVING_HOURS = 11  # Maximum 11 heures de conduite
    MAX_DUTY_WINDOW_HOURS = 14  # Fenêtre de 14 heures pour conduire
    BREAK_REQUIRED_AFTER_HOURS = 8  # Pause obligatoire après 8h de conduite
    BREAK_DURATION_MINUTES = 30  # Durée de la pause obligatoire
    CYCLE_70_HOURS = 70  # Cycle de 70 heures
    CYCLE_60_HOURS = 60  # Cycle de 60 heures
    CYCLE_8_DAYS = 8  # 70h sur 8 jours
    CYCLE_7_DAYS = 7  # 60h sur 7 jours
    RESTART_HOURS = 34  # Heures de repos pour restart
    MIN_REST_HOURS = 10  # Minimum 10h de repos
    
    @staticmethod
    def get_driver_current_status(driver) -> Dict:
        """
        Récupère le statut HOS actuel du conducteur
        
        Returns:
            Dict avec les informations du statut actuel
        """
        today = timezone.now().date()
        
        # Obtenir le log ELD d'aujourd'hui
        eld_log = ELDLog.objects.filter(
            driver=driver,
            log_date=today
        ).first()
        
        if not eld_log:
            # Créer un nouveau log pour aujourd'hui
            eld_log = HOSService._create_daily_log(driver, today)
        
        # Obtenir l'entrée de statut actuelle (sans end_time)
        current_entry = DutyStatusEntry.objects.filter(
            eld_log=eld_log,
            end_time__isnull=True
        ).first()
        
        if current_entry:
            duration = timezone.now() - current_entry.start_time
            current_status = {
                'status': current_entry.status,
                'start_time': current_entry.start_time,
                'duration_seconds': duration.total_seconds(),
                'duration_hours': duration.total_seconds() / 3600,
                'location': current_entry.location,
                'remarks': current_entry.remarks
            }
        else:
            current_status = {
                'status': 'OFF_DUTY',
                'start_time': None,
                'duration_seconds': 0,
                'duration_hours': 0,
                'location': 'Unknown',
                'remarks': ''
            }
        
        return {
            'current_status': current_status,
            'eld_log': eld_log
        }
    
    @staticmethod
    def change_duty_status(driver, new_status: str, location: str = None, 
                          latitude: float = None, longitude: float = None, 
                          remarks: str = '') -> Tuple[bool, str, DutyStatusEntry]:
        """
        Change le statut de service du conducteur
        
        Args:
            driver: Le conducteur
            new_status: Le nouveau statut (OFF_DUTY, SLEEPER_BERTH, DRIVING, ON_DUTY_NOT_DRIVING)
            location: Localisation textuelle
            latitude: Latitude GPS
            longitude: Longitude GPS
            remarks: Remarques additionnelles
            
        Returns:
            Tuple (success, message, entry)
        """
        try:
            now = timezone.now()
            today = now.date()
            
            # Obtenir ou créer le log ELD d'aujourd'hui
            eld_log = ELDLog.objects.filter(
                driver=driver,
                log_date=today
            ).first()
            
            if not eld_log:
                eld_log = HOSService._create_daily_log(driver, today)
            
            # Terminer l'entrée de statut précédente si elle existe
            previous_entry = DutyStatusEntry.objects.filter(
                eld_log=eld_log,
                end_time__isnull=True
            ).first()
            
            if previous_entry:
                previous_entry.end_time = now
                previous_entry.save()
            
            # Vérifier si le changement de statut est autorisé
            can_change, violation_message = HOSService._can_change_status(
                eld_log, new_status, previous_entry
            )
            
            # Créer la nouvelle entrée de statut
            new_entry = DutyStatusEntry.objects.create(
                eld_log=eld_log,
                trip=driver.current_trip if hasattr(driver, 'current_trip') else None,
                status=new_status,
                start_time=now,
                end_time=None,  # Sera rempli lors du prochain changement
                location=location or 'Unknown',
                latitude=latitude,
                longitude=longitude,
                remarks=remarks
            )
            
            # Recalculer les totaux du jour
            eld_log.calculate_daily_totals()
            
            # Enregistrer une violation si nécessaire
            if not can_change:
                HOSService._create_violation(
                    driver, eld_log, 'DUTY_LIMIT', 
                    violation_message, now
                )
                return False, violation_message, new_entry
            
            return True, 'Status changed successfully', new_entry
            
        except Exception as e:
            logger.error(f"Error changing duty status: {str(e)}")
            return False, f"Error: {str(e)}", None
    
    @staticmethod
    def _can_change_status(eld_log, new_status: str, previous_entry) -> Tuple[bool, str]:
        """
        Vérifie si le changement de statut est autorisé selon les règles HOS
        
        Returns:
            Tuple (can_change, violation_message)
        """
        # Si on passe à DRIVING, vérifier toutes les limites
        if new_status == 'DRIVING':
            # Vérifier limite de 11 heures de conduite
            if eld_log.driving_hours >= HOSService.MAX_DRIVING_HOURS:
                return False, f"Cannot drive: 11-hour driving limit reached ({eld_log.driving_hours}h)"
            
            # Vérifier fenêtre de 14 heures
            if eld_log.total_duty_hours >= HOSService.MAX_DUTY_WINDOW_HOURS:
                return False, f"Cannot drive: 14-hour duty window exceeded ({eld_log.total_duty_hours}h)"
            
            # Vérifier pause de 30 minutes après 8h de conduite
            if eld_log.driving_hours >= HOSService.BREAK_REQUIRED_AFTER_HOURS:
                last_break = HOSService._get_last_break(eld_log)
                if not last_break or last_break.duration_minutes < HOSService.BREAK_DURATION_MINUTES:
                    return False, "Cannot drive: 30-minute break required after 8 hours of driving"
            
            # Vérifier cycle 70h/8j
            if eld_log.cycle_hours_used >= eld_log.cycle_hours_available:
                return False, f"Cannot drive: Cycle limit reached ({eld_log.cycle_hours_used}h / {eld_log.cycle_hours_available}h)"
        
        return True, ""
    
    @staticmethod
    def _get_last_break(eld_log) -> DutyStatusEntry:
        """Obtient la dernière pause du conducteur"""
        return DutyStatusEntry.objects.filter(
            eld_log=eld_log,
            status__in=['OFF_DUTY', 'SLEEPER_BERTH'],
            end_time__isnull=False
        ).order_by('-end_time').first()
    
    @staticmethod
    def _create_daily_log(driver, log_date) -> ELDLog:
        """Crée un nouveau log ELD quotidien"""
        # Calculer les heures du cycle
        cycle_hours = HOSService.calculate_cycle_hours(driver, log_date)
        
        # Déterminer le cycle de la compagnie
        max_cycle_hours = HOSService.CYCLE_70_HOURS
        if driver.company and driver.company.operation_schedule == '7_DAY':
            max_cycle_hours = HOSService.CYCLE_60_HOURS
        
        trip = driver.current_trip if hasattr(driver, 'current_trip') else None
        vehicle_number = 'N/A'
        
        if driver.has_assigned_vehicle:
            vehicle_number = driver.assigned_vehicle.vehicle_number
        
        eld_log = ELDLog.objects.create(
            driver=driver,
            trip=trip,
            log_date=log_date,
            vehicle_number=vehicle_number,
            cycle_hours_used=cycle_hours,
            cycle_hours_available=max_cycle_hours - cycle_hours
        )
        
        return eld_log
    
    @staticmethod
    def calculate_cycle_hours(driver, target_date) -> float:
        """
        Calcule les heures utilisées dans le cycle actuel (70h/8j ou 60h/7j)
        
        Args:
            driver: Le conducteur
            target_date: La date cible
            
        Returns:
            Total des heures dans le cycle
        """
        # Déterminer le nombre de jours du cycle
        cycle_days = HOSService.CYCLE_8_DAYS
        if driver.company and driver.company.operation_schedule == '7_DAY':
            cycle_days = HOSService.CYCLE_7_DAYS
        
        # Calculer la date de début du cycle
        start_date = target_date - timedelta(days=cycle_days - 1)
        
        # Récupérer tous les logs ELD dans le cycle
        logs = ELDLog.objects.filter(
            driver=driver,
            log_date__gte=start_date,
            log_date__lte=target_date
        )
        
        total_hours = 0
        for log in logs:
            total_hours += float(log.driving_hours)
            total_hours += float(log.on_duty_not_driving_hours)
        
        return round(total_hours, 2)
    
    @staticmethod
    def check_violations(eld_log) -> List[Dict]:
        """
        Vérifie toutes les violations HOS possibles
        
        Returns:
            Liste des violations détectées
        """
        violations = []
        
        # Vérifier limite de 11 heures de conduite
        if eld_log.driving_hours > HOSService.MAX_DRIVING_HOURS:
            violations.append({
                'type': 'DRIVING_LIMIT',
                'severity': 'HIGH',
                'message': f"11-hour driving limit exceeded: {eld_log.driving_hours}h"
            })
        
        # Vérifier fenêtre de 14 heures
        if eld_log.total_duty_hours > HOSService.MAX_DUTY_WINDOW_HOURS:
            violations.append({
                'type': 'DUTY_LIMIT',
                'severity': 'HIGH',
                'message': f"14-hour duty window exceeded: {eld_log.total_duty_hours}h"
            })
        
        # Vérifier cycle
        if eld_log.cycle_hours_used > eld_log.cycle_hours_available:
            violations.append({
                'type': 'CYCLE_LIMIT',
                'severity': 'CRITICAL',
                'message': f"Cycle limit exceeded: {eld_log.cycle_hours_used}h"
            })
        
        return violations
    
    @staticmethod
    def _create_violation(driver, eld_log, violation_type: str, 
                         description: str, violation_time):
        """Crée une entrée de violation HOS"""
        severity = 'HIGH'
        if violation_type == 'CYCLE_LIMIT':
            severity = 'CRITICAL'
        
        HOSViolation.objects.create(
            driver=driver,
            eld_log=eld_log,
            violation_type=violation_type,
            severity=severity,
            description=description,
            violation_time=violation_time
        )
    
    @staticmethod
    def get_available_hours(driver) -> Dict:
        """
        Calcule les heures disponibles pour le conducteur
        
        Returns:
            Dict avec les heures disponibles
        """
        status_info = HOSService.get_driver_current_status(driver)
        eld_log = status_info['eld_log']
        
        return {
            'driving_hours_used': float(eld_log.driving_hours),
            'driving_hours_remaining': max(0, HOSService.MAX_DRIVING_HOURS - float(eld_log.driving_hours)),
            'duty_hours_used': float(eld_log.total_duty_hours),
            'duty_hours_remaining': max(0, HOSService.MAX_DUTY_WINDOW_HOURS - float(eld_log.total_duty_hours)),
            'cycle_hours_used': float(eld_log.cycle_hours_used),
            'cycle_hours_remaining': float(eld_log.cycle_hours_available),
            'break_required': eld_log.driving_hours >= HOSService.BREAK_REQUIRED_AFTER_HOURS
        }
    
    @staticmethod
    def certify_log(eld_log, signature_data: str = '') -> Tuple[bool, str]:
        """
        Certifie un log ELD (signature électronique du conducteur)
        
        Returns:
            Tuple (success, message)
        """
        if eld_log.is_certified:
            return False, "Log already certified"
        
        eld_log.is_certified = True
        eld_log.certified_at = timezone.now()
        eld_log.signature = signature_data
        eld_log.save()
        
        return True, "Log certified successfully"
