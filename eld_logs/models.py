from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User
from trips.models import Trip
import uuid
from datetime import timedelta

class ELDLog(models.Model):
    """Journal de bord électronique quotidien"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name='eld_logs'
    )
    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='eld_logs'
    )
    
    # Date and vehicle info
    log_date = models.DateField()
    vehicle_number = models.CharField(max_length=20)
    trailer_number = models.CharField(max_length=20, blank=True)
    shipping_document = models.CharField(max_length=50, blank=True)
    
    # Daily totals (in hours)
    total_miles = models.IntegerField(default=0)
    odometer_start = models.IntegerField(null=True, blank=True)
    odometer_end = models.IntegerField(null=True, blank=True)
    
    # Hours by duty status
    off_duty_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    sleeper_berth_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    driving_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    on_duty_not_driving_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    
    # Cycle information
    cycle_hours_used = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    cycle_hours_available = models.DecimalField(max_digits=4, decimal_places=2, default=70)
    
    # Compliance flags
    has_violations = models.BooleanField(default=False)
    violation_notes = models.TextField(blank=True)
    
    # Certification
    is_certified = models.BooleanField(default=False)
    certified_at = models.DateTimeField(null=True, blank=True)
    signature = models.TextField(blank=True)  # Digital signature data
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eld_logs_created',
        help_text="Utilisateur qui a créé ce journal ELD"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eld_logs_updated',
        help_text="Dernier utilisateur qui a modifié ce journal ELD"
    )
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['driver', 'log_date']
        ordering = ['-log_date']
        indexes = [
            models.Index(fields=['driver', 'log_date']),
            models.Index(fields=['trip', 'log_date']),
            models.Index(fields=['has_violations']),
        ]
    
    def __str__(self):
        return f"ELD Log - {self.driver.get_full_name()} - {self.log_date}"
    
    @property
    def total_duty_hours(self):
        """Total des heures de service pour la journée"""
        return (self.driving_hours + self.on_duty_not_driving_hours)
    
    @property
    def remaining_drive_time(self):
        """Temps de conduite restant pour la journée"""
        return max(0, 11 - float(self.driving_hours))
    
    @property
    def remaining_duty_time(self):
        """Temps de service restant pour la journée"""
        return max(0, 14 - float(self.total_duty_hours))
    
    def calculate_daily_totals(self):
        """Recalcule les totaux quotidiens à partir des entrées"""
        entries = self.duty_entries.all()
        
        totals = {
            'OFF_DUTY': 0,
            'SLEEPER_BERTH': 0,
            'DRIVING': 0,
            'ON_DUTY_NOT_DRIVING': 0,
        }
        
        for entry in entries:
            duration_hours = entry.duration_hours
            totals[entry.status] += duration_hours
        
        self.off_duty_hours = totals['OFF_DUTY']
        self.sleeper_berth_hours = totals['SLEEPER_BERTH']
        self.driving_hours = totals['DRIVING']
        self.on_duty_not_driving_hours = totals['ON_DUTY_NOT_DRIVING']
        
        # Check for violations
        self.check_violations()
        
        self.save()
    
    def check_violations(self):
        """Vérifie les violations HOS"""
        violations = []
        
        # 11-hour driving limit
        if self.driving_hours > 11:
            violations.append(f"Driving time exceeded: {self.driving_hours} hours (limit: 11)")
        
        # 14-hour duty limit
        if self.total_duty_hours > 14:
            violations.append(f"Duty time exceeded: {self.total_duty_hours} hours (limit: 14)")
        
        # 70-hour cycle limit
        if self.cycle_hours_used > 70:
            violations.append(f"Cycle hours exceeded: {self.cycle_hours_used} hours (limit: 70)")
        
        self.has_violations = len(violations) > 0
        self.violation_notes = "; ".join(violations)

class DutyStatusEntry(models.Model):
    """Entrée de statut de service dans un journal ELD"""
    
    STATUS_CHOICES = [
        ('OFF_DUTY', 'Hors service'),
        ('SLEEPER_BERTH', 'Couchette'),
        ('DRIVING', 'Conduite'),
        ('ON_DUTY_NOT_DRIVING', 'En service (non-conduite)'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name='duty_entries',
        null=True,
        blank=True
    )  # Ajout de null=True, blank=True selon conception
    eld_log = models.ForeignKey(
        ELDLog,
        on_delete=models.CASCADE,
        related_name='duty_entries'
    )
    
    # Time and status - Garder DateTimeField (plus correct que TimeField de la conception)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES)
    
    # Location information
    location = models.CharField(max_length=200)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    # Additional info
    remarks = models.TextField(blank=True)
    odometer_reading = models.IntegerField(null=True, blank=True)
    engine_hours = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    
    # Editing tracking
    is_edited = models.BooleanField(default=False)
    edit_reason = models.CharField(max_length=200, blank=True)
    edited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='edited_duty_entries'
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='duty_entries_created',
        help_text="Utilisateur qui a créé cette entrée de statut"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='duty_entries_updated',
        help_text="Dernier utilisateur qui a modifié cette entrée de statut"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['eld_log', 'start_time']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.get_status_display()} - {self.start_time.strftime('%H:%M')} to {self.end_time.strftime('%H:%M')}"
    
    @property
    def duration(self):
        """Durée de l'entrée"""
        return self.end_time - self.start_time
    
    @property
    def duration_hours(self):
        """Durée en heures"""
        return self.duration.total_seconds() / 3600
    
    @property
    def duration_minutes(self):
        """Durée en minutes"""
        return self.duration.total_seconds() / 60
    
    def clean(self):
        """Validation des données"""
        from django.core.exceptions import ValidationError
        
        if self.start_time >= self.end_time:
            raise ValidationError("Start time must be before end time")
        
        # Check for overlapping entries
        overlapping = DutyStatusEntry.objects.filter(
            eld_log=self.eld_log
        ).exclude(id=self.id).filter(
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        )
        
        if overlapping.exists():
            raise ValidationError("This entry overlaps with existing entries")

class HOSViolation(models.Model):
    """Violations des règles HOS"""
    
    VIOLATION_TYPE_CHOICES = [
        ('DRIVING_LIMIT', '11-hour driving limit exceeded'),
        ('DUTY_LIMIT', '14-hour duty limit exceeded'),
        ('CYCLE_LIMIT', '70-hour cycle limit exceeded'),
        ('BREAK_REQUIRED', '30-minute break required'),
        ('REST_REQUIRED', '10-hour rest period required'),
    ]
    
    SEVERITY_CHOICES = [
        ('LOW', 'Faible'),
        ('MEDIUM', 'Moyen'),
        ('HIGH', 'Élevé'),
        ('CRITICAL', 'Critique'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    eld_log = models.ForeignKey(
        ELDLog,
        on_delete=models.CASCADE,
        related_name='violations'
    )
    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='hos_violations'
    )
    
    violation_type = models.CharField(max_length=20, choices=VIOLATION_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    description = models.TextField()
    
    # Time information
    violation_time = models.DateTimeField()
    duration_minutes = models.IntegerField(null=True, blank=True)
    
    # Resolution
    is_resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_violations'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='violations_created',
        help_text="Utilisateur qui a créé cette violation"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='violations_updated',
        help_text="Dernier utilisateur qui a modifié cette violation"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-violation_time']
        indexes = [
            models.Index(fields=['driver', 'violation_time']),
            models.Index(fields=['violation_type']),
            models.Index(fields=['is_resolved']),
        ]
    
    def __str__(self):
        return f"{self.get_violation_type_display()} - {self.driver.get_full_name()}"

class ELDExport(models.Model):
    """Exports de journaux ELD pour les autorités"""
    
    EXPORT_TYPE_CHOICES = [
        ('DOT_INSPECTION', 'Inspection DOT'),
        ('COMPANY_REPORT', 'Rapport entreprise'),
        ('DRIVER_REQUEST', 'Demande conducteur'),
        ('AUDIT', 'Audit'),
    ]
    
    FORMAT_CHOICES = [
        ('PDF', 'PDF'),
        ('CSV', 'CSV'),
        ('XML', 'XML'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='eld_exports'
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='requested_exports'
    )
    
    # Export parameters
    export_type = models.CharField(max_length=20, choices=EXPORT_TYPE_CHOICES)
    format = models.CharField(max_length=5, choices=FORMAT_CHOICES, default='PDF')
    start_date = models.DateField()
    end_date = models.DateField()
    
    # File information
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    
    # Status
    is_completed = models.BooleanField(default=False)
    completion_time = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exports_created',
        help_text="Utilisateur qui a créé cet export"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exports_updated',
        help_text="Dernier utilisateur qui a modifié cet export"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"ELD Export - {self.driver.get_full_name()} ({self.start_date} to {self.end_date})"
