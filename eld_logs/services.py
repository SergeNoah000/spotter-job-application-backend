"""
Services pour la gestion des règles HOS (Hours of Service)
Implémente la logique métier pour les calculs et validations HOS selon la réglementation FMCSA
"""

from datetime import datetime, timedelta, time
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from django.db.models import Sum, Q
from django.utils import timezone
from .models import ELDLog, DutyStatusEntry, HOSViolation


class HOSRulesEngine:
    """
    Moteur de règles pour les Hours of Service (HOS) selon la réglementation FMCSA
    
    Règles principales:
    - Limite de conduite: 11 heures maximum après 10 heures consécutives hors service
    - Limite de service: 14 heures maximum de fenêtre de service
    - Pause obligatoire: 30 minutes après 8 heures de conduite
    - Repos obligatoire: 10 heures consécutives hors service avant un nouveau cycle
    - Limite de cycle: 60/70 heures sur 7/8 jours
    """
    
    # Constantes HOS
    MAX_DRIVING_HOURS = 11
    MAX_DUTY_HOURS = 14
    REQUIRED_BREAK_MINUTES = 30
    BREAK_REQUIRED_AFTER_HOURS = 8
    REQUIRED_REST_HOURS = 10
    CYCLE_70_HOURS = 70
    CYCLE_60_HOURS = 60
    CYCLE_70_DAYS = 8
    CYCLE_60_DAYS = 7
    
    def __init__(self, driver):
        """
        Initialise le moteur HOS pour un conducteur spécifique
        
        Args:
            driver: Instance du User (conducteur)
        """
        self.driver = driver
        self.today = timezone.now().date()
    
    def get_current_hos_status(self) -> Dict:
        """
        Calcule le statut HOS actuel du conducteur
        
        Returns:
            Dict contenant tous les temps disponibles et utilisés
        """
        # Obtenir le log ELD du jour
        today_log = self._get_or_create_today_log()
        
        # Calculer les temps utilisés aujourd'hui
        daily_times = self._calculate_daily_times(today_log)
        
        # Calculer les temps du cycle (7/8 jours)
        cycle_times = self._calculate_cycle_times()
        
        # Vérifier la pause obligatoire de 30 minutes
        break_status = self._check_break_requirement(today_log)
        
        # Calculer le temps depuis le dernier repos
        rest_status = self._calculate_rest_status()
        
        # Calculer les temps disponibles
        available_times = self._calculate_available_times(
            daily_times, cycle_times, rest_status
        )
        
        # Détecter les violations
        violations = self._detect_violations(today_log, daily_times, cycle_times)
        
        return {
            'driver_name': self.driver.get_full_name(),
            'current_date': self.today.isoformat(),
            'current_status': self._get_current_duty_status(),
            
            # Temps utilisés aujourd'hui
            'daily': {
                'driving_hours': float(daily_times['driving']),
                'duty_hours': float(daily_times['duty']),
                'on_duty_hours': float(daily_times['on_duty']),
                'off_duty_hours': float(daily_times['off_duty']),
            },
            
            # Temps disponibles
            'available': {
                'driving_hours': float(available_times['driving']),
                'duty_hours': float(available_times['duty']),
                'cycle_hours': float(available_times['cycle']),
            },
            
            # Statut de la pause
            'break': {
                'required': break_status['required'],
                'completed': break_status['completed'],
                'time_since_last_break': break_status['time_since_last_break'],
            },
            
            # Statut du repos
            'rest': {
                'hours_since_last_rest': float(rest_status['hours_since_last_rest']),
                'needs_rest': rest_status['needs_rest'],
                'in_rest_period': rest_status['in_rest_period'],
            },
            
            # Cycle (70 heures sur 8 jours)
            'cycle': {
                'hours_used': float(cycle_times['hours_used']),
                'hours_available': float(cycle_times['hours_available']),
                'days_in_cycle': cycle_times['days_count'],
            },
            
            # Violations
            'violations': violations,
            'has_violations': len(violations) > 0,
        }
    
    def can_start_driving(self) -> Tuple[bool, str]:
        """
        Vérifie si le conducteur peut commencer à conduire
        
        Returns:
            Tuple (can_drive: bool, reason: str)
        """
        status = self.get_current_hos_status()
        
        # Vérifier le temps de conduite disponible
        if status['available']['driving_hours'] <= 0:
            return False, "Limite de conduite quotidienne atteinte (11 heures)"
        
        # Vérifier le temps de service disponible
        if status['available']['duty_hours'] <= 0:
            return False, "Limite de service quotidienne atteinte (14 heures)"
        
        # Vérifier le cycle
        if status['available']['cycle_hours'] <= 0:
            return False, "Limite de cycle atteinte (70 heures sur 8 jours)"
        
        # Vérifier la pause obligatoire
        if status['break']['required'] and not status['break']['completed']:
            return False, "Pause de 30 minutes obligatoire après 8 heures de conduite"
        
        # Vérifier le repos obligatoire
        if status['rest']['needs_rest']:
            return False, "Repos de 10 heures obligatoire"
        
        return True, "Autorisation de conduire accordée"
    
    def calculate_available_driving_time(self) -> Dict:
        """
        Calcule le temps de conduite disponible en tenant compte de toutes les contraintes
        
        Returns:
            Dict avec les différentes limites de temps
        """
        status = self.get_current_hos_status()
        
        return {
            'by_daily_limit': status['available']['driving_hours'],
            'by_duty_window': status['available']['duty_hours'],
            'by_cycle_limit': status['available']['cycle_hours'],
            'effective_available': min(
                status['available']['driving_hours'],
                status['available']['duty_hours'],
                status['available']['cycle_hours']
            ),
            'limiting_factor': self._get_limiting_factor(status),
        }
    
    def predict_violation(self, planned_driving_hours: float) -> List[Dict]:
        """
        Prédit les violations potentielles pour un temps de conduite planifié
        
        Args:
            planned_driving_hours: Heures de conduite planifiées
            
        Returns:
            Liste des violations potentielles
        """
        status = self.get_current_hos_status()
        potential_violations = []
        
        # Vérifier la limite quotidienne de conduite
        new_driving_hours = status['daily']['driving_hours'] + planned_driving_hours
        if new_driving_hours > self.MAX_DRIVING_HOURS:
            potential_violations.append({
                'type': 'DRIVING_LIMIT',
                'severity': 'HIGH',
                'description': f"Dépassement de la limite de conduite quotidienne: {new_driving_hours:.1f}h / {self.MAX_DRIVING_HOURS}h",
                'excess_hours': new_driving_hours - self.MAX_DRIVING_HOURS,
            })
        
        # Vérifier la limite de service
        new_duty_hours = status['daily']['duty_hours'] + planned_driving_hours
        if new_duty_hours > self.MAX_DUTY_HOURS:
            potential_violations.append({
                'type': 'DUTY_LIMIT',
                'severity': 'HIGH',
                'description': f"Dépassement de la fenêtre de service: {new_duty_hours:.1f}h / {self.MAX_DUTY_HOURS}h",
                'excess_hours': new_duty_hours - self.MAX_DUTY_HOURS,
            })
        
        # Vérifier le cycle
        new_cycle_hours = status['cycle']['hours_used'] + planned_driving_hours
        if new_cycle_hours > self.CYCLE_70_HOURS:
            potential_violations.append({
                'type': 'CYCLE_LIMIT',
                'severity': 'CRITICAL',
                'description': f"Dépassement du cycle: {new_cycle_hours:.1f}h / {self.CYCLE_70_HOURS}h",
                'excess_hours': new_cycle_hours - self.CYCLE_70_HOURS,
            })
        
        return potential_violations
    
    def record_duty_status_change(
        self, 
        status: str, 
        location: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        remarks: str = ""
    ) -> DutyStatusEntry:
        """
        Enregistre un changement de statut de service
        
        Args:
            status: Le nouveau statut
            location: La localisation
            latitude: Latitude optionnelle
            longitude: Longitude optionnelle
            remarks: Remarques optionnelles
            
        Returns:
            L'entrée DutyStatusEntry créée
        """
        now = timezone.now()
        today_log = self._get_or_create_today_log()
        
        # Terminer l'entrée en cours si elle existe
        last_entry = DutyStatusEntry.objects.filter(
            eld_log=today_log
        ).order_by('-start_time').first()
        
        if last_entry and last_entry.end_time is None:
            last_entry.end_time = now
            last_entry.save()
        
        # Créer la nouvelle entrée
        entry = DutyStatusEntry.objects.create(
            eld_log=today_log,
            start_time=now,
            end_time=None,  # Sera mis à jour lors du prochain changement
            status=status,
            location=location,
            latitude=latitude,
            longitude=longitude,
            remarks=remarks,
            created_by=self.driver
        )
        
        # Recalculer les totaux
        today_log.calculate_daily_totals()
        
        return entry
    
    def _get_or_create_today_log(self) -> ELDLog:
        """Obtient ou crée le log ELD du jour"""
        log, created = ELDLog.objects.get_or_create(
            driver=self.driver,
            log_date=self.today,
            defaults={
                'vehicle_number': '',  # Sera mis à jour
                'created_by': self.driver
            }
        )
        return log
    
    def _calculate_daily_times(self, eld_log: ELDLog) -> Dict:
        """Calcule les temps utilisés aujourd'hui"""
        return {
            'driving': eld_log.driving_hours,
            'on_duty': eld_log.on_duty_not_driving_hours,
            'duty': eld_log.driving_hours + eld_log.on_duty_not_driving_hours,
            'off_duty': eld_log.off_duty_hours,
            'sleeper': eld_log.sleeper_berth_hours,
        }
    
    def _calculate_cycle_times(self) -> Dict:
        """Calcule les temps du cycle (8 jours glissants)"""
        cycle_start = self.today - timedelta(days=self.CYCLE_70_DAYS - 1)
        
        logs = ELDLog.objects.filter(
            driver=self.driver,
            log_date__gte=cycle_start,
            log_date__lte=self.today
        )
        
        total_duty_hours = sum(
            float(log.driving_hours + log.on_duty_not_driving_hours)
            for log in logs
        )
        
        return {
            'hours_used': Decimal(str(total_duty_hours)),
            'hours_available': Decimal(str(max(0, self.CYCLE_70_HOURS - total_duty_hours))),
            'days_count': logs.count(),
        }
    
    def _check_break_requirement(self, eld_log: ELDLog) -> Dict:
        """Vérifie si une pause de 30 minutes est requise"""
        # Obtenir les entrées de conduite aujourd'hui
        driving_entries = eld_log.duty_entries.filter(
            status='DRIVING'
        ).order_by('start_time')
        
        if not driving_entries.exists():
            return {
                'required': False,
                'completed': True,
                'time_since_last_break': 0,
            }
        
        # Calculer le temps de conduite depuis la dernière pause
        total_driving_since_break = Decimal('0')
        last_break_time = None
        
        for entry in driving_entries:
            total_driving_since_break += Decimal(str(entry.duration_hours))
            
            # Vérifier s'il y a eu une pause après cette entrée
            next_entries = eld_log.duty_entries.filter(
                start_time__gt=entry.end_time,
                status__in=['OFF_DUTY', 'SLEEPER_BERTH']
            )
            
            for break_entry in next_entries:
                if break_entry.duration_minutes >= self.REQUIRED_BREAK_MINUTES:
                    total_driving_since_break = Decimal('0')
                    last_break_time = break_entry.end_time
                    break
        
        break_required = total_driving_since_break >= self.BREAK_REQUIRED_AFTER_HOURS
        
        return {
            'required': break_required,
            'completed': not break_required,
            'time_since_last_break': float(total_driving_since_break),
        }
    
    def _calculate_rest_status(self) -> Dict:
        """Calcule le statut du repos obligatoire"""
        # Trouver la dernière période de repos de 10 heures
        last_logs = ELDLog.objects.filter(
            driver=self.driver,
            log_date__lte=self.today
        ).order_by('-log_date')[:3]  # Regarder les 3 derniers jours
        
        hours_since_rest = Decimal('0')
        in_rest_period = False
        
        for log in last_logs:
            # Vérifier s'il y a une période de repos suffisante
            rest_entries = log.duty_entries.filter(
                status__in=['OFF_DUTY', 'SLEEPER_BERTH']
            ).order_by('-start_time')
            
            for entry in rest_entries:
                if entry.duration_hours >= self.REQUIRED_REST_HOURS:
                    # Repos trouvé
                    time_since_rest = timezone.now() - entry.end_time
                    hours_since_rest = Decimal(str(time_since_rest.total_seconds() / 3600))
                    
                    # Vérifier si actuellement en repos
                    if entry.end_time > timezone.now():
                        in_rest_period = True
                    
                    return {
                        'hours_since_last_rest': hours_since_rest,
                        'needs_rest': hours_since_rest >= self.MAX_DUTY_HOURS,
                        'in_rest_period': in_rest_period,
                    }
        
        # Aucun repos trouvé récemment
        return {
            'hours_since_last_rest': Decimal('24'),  # Par défaut, considérer 24h
            'needs_rest': True,
            'in_rest_period': False,
        }
    
    def _calculate_available_times(
        self, 
        daily_times: Dict, 
        cycle_times: Dict,
        rest_status: Dict
    ) -> Dict:
        """Calcule les temps disponibles"""
        driving_available = max(0, self.MAX_DRIVING_HOURS - float(daily_times['driving']))
        duty_available = max(0, self.MAX_DUTY_HOURS - float(daily_times['duty']))
        cycle_available = float(cycle_times['hours_available'])
        
        # Si repos requis, temps disponible = 0
        if rest_status['needs_rest'] and not rest_status['in_rest_period']:
            driving_available = 0
            duty_available = 0
        
        return {
            'driving': Decimal(str(driving_available)),
            'duty': Decimal(str(duty_available)),
            'cycle': Decimal(str(cycle_available)),
        }
    
    def _get_current_duty_status(self) -> str:
        """Obtient le statut de service actuel"""
        today_log = self._get_or_create_today_log()
        last_entry = DutyStatusEntry.objects.filter(
            eld_log=today_log
        ).order_by('-start_time').first()
        
        if last_entry:
            return last_entry.get_status_display()
        return "OFF_DUTY"
    
    def _detect_violations(
        self, 
        eld_log: ELDLog, 
        daily_times: Dict, 
        cycle_times: Dict
    ) -> List[Dict]:
        """Détecte les violations HOS"""
        violations = []
        
        # Limite de conduite quotidienne
        if daily_times['driving'] > self.MAX_DRIVING_HOURS:
            violations.append({
                'type': 'DRIVING_LIMIT',
                'severity': 'HIGH',
                'description': f"Limite de conduite dépassée: {daily_times['driving']:.1f}h / {self.MAX_DRIVING_HOURS}h"
            })
        
        # Limite de service quotidienne
        if daily_times['duty'] > self.MAX_DUTY_HOURS:
            violations.append({
                'type': 'DUTY_LIMIT',
                'severity': 'HIGH',
                'description': f"Fenêtre de service dépassée: {daily_times['duty']:.1f}h / {self.MAX_DUTY_HOURS}h"
            })
        
        # Limite de cycle
        if cycle_times['hours_used'] > self.CYCLE_70_HOURS:
            violations.append({
                'type': 'CYCLE_LIMIT',
                'severity': 'CRITICAL',
                'description': f"Cycle dépassé: {cycle_times['hours_used']:.1f}h / {self.CYCLE_70_HOURS}h"
            })
        
        return violations
    
    def _get_limiting_factor(self, status: Dict) -> str:
        """Détermine le facteur limitant"""
        available = status['available']
        
        min_time = min(
            available['driving_hours'],
            available['duty_hours'],
            available['cycle_hours']
        )
        
        if min_time == available['driving_hours']:
            return 'daily_driving_limit'
        elif min_time == available['duty_hours']:
            return 'daily_duty_window'
        else:
            return 'cycle_limit'


class ELDLogService:
    """Service pour la gestion des logs ELD"""
    
    @staticmethod
    def create_daily_log(driver, log_date, vehicle):
        """Crée un nouveau log ELD quotidien"""
        log = ELDLog.objects.create(
            driver=driver,
            log_date=log_date,
            vehicle_number=vehicle.vehicle_number if vehicle else '',
            created_by=driver
        )
        return log
    
    @staticmethod
    def certify_log(log, signature_data):
        """Certifie un log ELD"""
        log.is_certified = True
        log.certified_at = timezone.now()
        log.signature = signature_data
        log.save()
        return log
    
    @staticmethod
    def get_driver_logs_for_period(driver, start_date, end_date):
        """Récupère les logs d'un conducteur pour une période"""
        return ELDLog.objects.filter(
            driver=driver,
            log_date__gte=start_date,
            log_date__lte=end_date
        ).order_by('-log_date')
