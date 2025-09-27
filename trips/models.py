from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from accounts.models import User
import uuid

class Vehicle(models.Model):
    """Modèle pour les véhicules"""
    
    VEHICLE_TYPE_CHOICES = [
        ('TRACTOR', 'Tracteur'),
        ('STRAIGHT_TRUCK', 'Camion porteur'),
        ('VAN', 'Fourgonnette'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle_number = models.CharField(max_length=20, unique=True)
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.IntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(2030)]
    )
    vin = models.CharField(max_length=17, unique=True)
    license_plate = models.CharField(max_length=15)
    vehicle_type = models.CharField(
        max_length=15,
        choices=VEHICLE_TYPE_CHOICES,
        default='TRACTOR'
    )
    company = models.ForeignKey(
        'accounts.Company',
        on_delete=models.CASCADE,
        related_name='vehicles'
    )
    
    # Conducteur assigné au véhicule (relation 1:1)
    assigned_driver = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_vehicle',
        limit_choices_to={'user_type': 'DRIVER'},
        help_text="Conducteur actuellement assigné à ce véhicule"
    )
    
    # Images du véhicule
    front_image = models.ImageField(
        upload_to='vehicles/front/',
        null=True,
        blank=True,
        help_text="Vue de face du véhicule"
    )
    side_image = models.ImageField(
        upload_to='vehicles/side/',
        null=True,
        blank=True,
        help_text="Vue de profil du véhicule"
    )
    rear_image = models.ImageField(
        upload_to='vehicles/rear/',
        null=True,
        blank=True,
        help_text="Vue arrière du véhicule"
    )
    
    # Statut opérationnel du véhicule
    STATUS_CHOICES = [
        ('AVAILABLE', 'Disponible'),
        ('IN_USE', 'En utilisation'),
        ('MAINTENANCE', 'En maintenance'),
        ('OUT_OF_SERVICE', 'Hors service'),
    ]
    
    operational_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='AVAILABLE',
        help_text="Statut opérationnel actuel du véhicule"
    )
    
    # Localisation actuelle (sera mise à jour en temps réel)
    current_latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True,
        help_text="Latitude actuelle du véhicule"
    )
    current_longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True,
        help_text="Longitude actuelle du véhicule"
    )
    last_location_update = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Dernière mise à jour de la position"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['vehicle_number']
    
    def __str__(self):
        return f"{self.vehicle_number} - {self.make} {self.model}"
    
    @property
    def current_location_display(self):
        """Affichage formaté de la position actuelle"""
        if self.current_latitude and self.current_longitude:
            return f"{self.current_latitude:.4f}, {self.current_longitude:.4f}"
        return "Position inconnue"
    
    @property
    def is_assigned(self):
        """Vérifie si le véhicule a un conducteur assigné"""
        return self.assigned_driver is not None
    
    @property
    def can_start_trip(self):
        """Vérifie si le véhicule peut commencer un voyage"""
        return (
            self.is_active and 
            self.is_assigned and 
            self.operational_status == 'AVAILABLE'
        )

class Trip(models.Model):
    """Modèle pour les voyages"""
    
    STATUS_CHOICES = [
        ('PLANNED', 'Planifié'),
        ('IN_PROGRESS', 'En cours'),
        ('COMPLETED', 'Terminé'),
        ('CANCELLED', 'Annulé'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trips'
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='trips',
        null=True,
        blank=True
    )
    
    # Trip locations
    current_location = models.CharField(max_length=200)
    current_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    pickup_location = models.CharField(max_length=200)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_time = models.DateTimeField(null=True, blank=True)
    
    dropoff_location = models.CharField(max_length=200)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_time = models.DateTimeField(null=True, blank=True)
    
    # Trip details
    current_cycle_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(70)]
    )
    total_distance = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True
    )
    estimated_duration = models.DurationField(null=True, blank=True)
    actual_duration = models.DurationField(null=True, blank=True)
    
    # Load information
    load_weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Weight in pounds"
    )
    trailer_number = models.CharField(max_length=20, blank=True)
    shipping_document = models.CharField(max_length=50, blank=True)
    
    # Trip status
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='PLANNED'
    )
    
    # Timestamps
    planned_start_time = models.DateTimeField()
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Route data (JSON field for storing calculated route)
    route_data = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['driver', 'status']),
            models.Index(fields=['planned_start_time']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Trip {self.id} - {self.driver.get_full_name()}"
    
    @property
    def is_active(self):
        return self.status in ['PLANNED', 'IN_PROGRESS']
    
    def get_total_driving_hours(self):
        """Calcule les heures de conduite totales pour ce voyage"""
        if self.total_distance:
            # Estimation: 55 mph moyenne
            return float(self.total_distance) / 55
        return 0

class RestStop(models.Model):
    """Modèle pour les arrêts de repos"""
    
    STOP_TYPE_CHOICES = [
        ('30_MIN_BREAK', 'Pause 30 min'),
        ('10_HOUR_REST', 'Repos 10h'),
        ('FUEL', 'Ravitaillement'),
        ('PICKUP', 'Ramassage'),
        ('DROPOFF', 'Livraison'),
        ('MEAL', 'Repas'),
        ('WEIGH_STATION', 'Station de pesage'),
        ('INSPECTION', 'Inspection'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name='rest_stops'
    )
    
    # Location details
    location = models.CharField(max_length=200)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    address = models.TextField(blank=True)
    
    # Stop details
    stop_type = models.CharField(max_length=20, choices=STOP_TYPE_CHOICES)
    planned_start_time = models.DateTimeField()
    planned_duration = models.DurationField()
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_duration = models.DurationField(null=True, blank=True)
    
    # Status
    is_mandatory = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)
    
    # Additional info
    notes = models.TextField(blank=True)
    fuel_gallons = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['planned_start_time']
        indexes = [
            models.Index(fields=['trip', 'planned_start_time']),
            models.Index(fields=['stop_type']),
        ]
    
    def __str__(self):
        return f"{self.get_stop_type_display()} - {self.location}"
    
    @property
    def duration_hours(self):
        """Retourne la durée en heures"""
        if self.actual_duration:
            return self.actual_duration.total_seconds() / 3600
        return self.planned_duration.total_seconds() / 3600

class TripWaypoint(models.Model):
    """Points de passage pour un voyage"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name='waypoints'
    )
    
    # Location
    name = models.CharField(max_length=200)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    
    # Order and timing
    sequence_order = models.PositiveIntegerField()
    estimated_arrival = models.DateTimeField()
    actual_arrival = models.DateTimeField(null=True, blank=True)
    
    # Distance from previous waypoint
    distance_from_previous = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['trip', 'sequence_order']
        unique_together = ['trip', 'sequence_order']
    
    def __str__(self):
        return f"{self.name} (#{self.sequence_order})"
