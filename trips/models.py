from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
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
    
    # Conducteur actuellement assigné (optionnel)
    current_driver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='current_vehicle',
        limit_choices_to={'user_type': 'DRIVER'},
        help_text="Conducteur actuellement assigné à ce véhicule"
    )
    
    # Date/heure de la dernière attribution
    last_assignment_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date et heure de la dernière attribution de conducteur"
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
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicles_created',
        help_text="Utilisateur qui a créé ce véhicule"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicles_updated',
        help_text="Dernier utilisateur qui a modifié ce véhicule"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['vehicle_number']
        indexes = [
            models.Index(fields=['current_driver']),
            models.Index(fields=['operational_status']),
            models.Index(fields=['company', 'operational_status']),
        ]
    
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
        return self.current_driver is not None
    
    @property
    def can_start_trip(self):
        """Vérifie si le véhicule peut commencer un voyage"""
        return (
            self.is_active and 
            self.operational_status in ['AVAILABLE', 'IN_USE']
        )
    
    def assign_driver(self, driver, assigned_by=None, notes=""):
        """
        Assigne un nouveau conducteur au véhicule
        
        Args:
            driver: L'utilisateur conducteur à assigner
            assigned_by: L'utilisateur qui fait l'attribution
            notes: Notes optionnelles sur l'attribution
        
        Returns:
            VehicleAssignment: L'objet d'attribution créé
        """
        # Fermer l'attribution précédente si elle existe
        current_assignment = self.get_current_assignment()
        if current_assignment:
            current_assignment.end_assignment(ended_by=assigned_by)
        
        # Créer la nouvelle attribution
        assignment = VehicleAssignment.objects.create(
            vehicle=self,
            driver=driver,
            assigned_by=assigned_by,
            notes=notes
        )
        
        # Mettre à jour le véhicule
        self.current_driver = driver
        self.last_assignment_date = timezone.now()
        if assigned_by:
            self.updated_by = assigned_by
        self.save()
        
        return assignment
    
    def unassign_driver(self, unassigned_by=None, reason=""):
        """
        Retire le conducteur actuellement assigné
        
        Args:
            unassigned_by: L'utilisateur qui retire l'attribution
            reason: Raison du retrait
        """
        current_assignment = self.get_current_assignment()
        if current_assignment:
            current_assignment.end_assignment(ended_by=unassigned_by, reason=reason)
        
        self.current_driver = None
        self.last_assignment_date = timezone.now()
        if unassigned_by:
            self.updated_by = unassigned_by
        self.save()
    
    def get_current_assignment(self):
        """Retourne l'attribution actuelle du véhicule"""
        return self.assignments.filter(end_date__isnull=True).first()
    
    def get_assignment_history(self, limit=10):
        """Retourne l'historique des attributions"""
        return self.assignments.order_by('-start_date')[:limit]
    
    def can_be_assigned_to(self, driver):
        """
        Vérifie si le véhicule peut être assigné à un conducteur donné
        
        Args:
            driver: Le conducteur à vérifier
            
        Returns:
            tuple: (bool, str) - (peut_être_assigné, raison_si_non)
        """
        if not self.is_active:
            return False, "Le véhicule n'est pas actif"
        
        if self.operational_status == 'OUT_OF_SERVICE':
            return False, "Le véhicule est hors service"
        
        if self.operational_status == 'MAINTENANCE':
            return False, "Le véhicule est en maintenance"
        
        if driver.user_type != 'DRIVER':
            return False, "L'utilisateur n'est pas un conducteur"
        
        if not hasattr(driver, 'company') or driver.company != self.company:
            return False, "Le conducteur n'appartient pas à la même entreprise"
        
        # Vérifier si le conducteur a déjà un véhicule assigné
        current_vehicle = Vehicle.objects.filter(current_driver=driver).first()
        if current_vehicle and current_vehicle != self:
            return False, f"Le conducteur est déjà assigné au véhicule {current_vehicle.vehicle_number}"
        
        return True, "Attribution possible"


class VehicleAssignment(models.Model):
    """
    Modèle pour tracker l'historique des attributions de véhicules aux conducteurs
    Permet de gérer les rotations et le team driving
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='vehicle_assignments',
        limit_choices_to={'user_type': 'DRIVER'}
    )
    
    # Période d'attribution
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    
    # Métadonnées d'attribution
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicle_assignments_made',
        help_text="Utilisateur qui a fait l'attribution"
    )
    ended_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicle_assignments_ended',
        help_text="Utilisateur qui a terminé l'attribution"
    )
    
    # Informations additionnelles
    notes = models.TextField(
        blank=True,
        help_text="Notes sur cette attribution (raison, conditions spéciales, etc.)"
    )
    end_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Raison de la fin d'attribution"
    )
    
    # Champs d'audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['vehicle', 'start_date']),
            models.Index(fields=['driver', 'start_date']),
            models.Index(fields=['start_date', 'end_date']),
        ]
    
    def __str__(self):
        status = "Actuelle" if not self.end_date else "Terminée"
        return f"{self.vehicle.vehicle_number} → {self.driver.get_full_name()} ({status})"
    
    @property
    def is_active(self):
        """Vérifie si l'attribution est actuellement active"""
        return self.end_date is None
    
    @property
    def duration(self):
        """Retourne la durée de l'attribution"""
        end_time = self.end_date or timezone.now()
        return end_time - self.start_date
    
    def end_assignment(self, ended_by=None, reason=""):
        """
        Termine l'attribution actuelle
        
        Args:
            ended_by: Utilisateur qui termine l'attribution
            reason: Raison de la fin d'attribution
        """
        if not self.end_date:  # Seulement si pas déjà terminée
            self.end_date = timezone.now()
            self.ended_by = ended_by
            self.end_reason = reason
            self.save()


class Trip(models.Model):
    """Modèle pour les voyages"""
    
    STATUS_CHOICES = [
        ('PLANNED', 'Planifié'),
        ('AT_PICKUP', 'Au ramassage'),
        ('IN_TRANSIT', 'En transit'),
        ('AT_DELIVERY', 'À la livraison'),
        ('COMPLETED', 'Terminé'),
        ('CANCELLED', 'Annulé'),
    ]
    
    PRIORITY_CHOICES = [
        ('LOW', 'Faible'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'Élevée'),
        ('URGENT', 'Urgent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Conducteur et véhicule
    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trips',
        limit_choices_to={'user_type': 'DRIVER'},
        help_text="Conducteur assigné au voyage"
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='trips',
        null=True,
        blank=True,
        help_text="Véhicule assigné au voyage"
    )
    
    # Informations générales du voyage
    trip_number = models.CharField(
        max_length=20, 
        unique=True,
        help_text="Numéro de voyage unique",
        null=True,
        blank=True
    )
    title = models.CharField(
        max_length=200,
        help_text="Titre descriptif du voyage",
        default="Deplacement normal"
    )
    description = models.TextField(
        blank=True,
        help_text="Description détaillée du voyage"
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='NORMAL',
        help_text="Priorité du voyage"
    )
    
    # Lieu de départ
    origin_address = models.CharField(
        max_length=300,
        help_text="Adresse de départ",
        default="Non spécifié"
    )
    origin_latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Latitude du point de départ",
        default=0.0
    )
    origin_longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Longitude du point de départ",
        default=0.0
    )
    origin_notes = models.TextField(
        blank=True,
        help_text="Notes spéciales pour le lieu de départ"
    )
    
    # Lieu d'arrivée
    destination_address = models.CharField(
        max_length=300,
        help_text="Adresse de destination",
        default="Non spécifié"
    )
    destination_latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Latitude du point d'arrivée",
        default=0.0
    )
    destination_longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Longitude du point d'arrivée",
        default=0.0
    )
    destination_notes = models.TextField(
        blank=True,
        help_text="Notes spéciales pour le lieu d'arrivée"
    )
    
    # Nouveau : Informations de ramassage (PICKUP)
    pickup_company = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nom de la compagnie au ramassage"
    )
    pickup_contact = models.CharField(
        max_length=100,
        blank=True,
        help_text="Contact au ramassage"
    )
    pickup_address = models.CharField(
        max_length=300,
        help_text="Adresse de ramassage",
        default="Non spécifié"
    )
    pickup_latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Latitude du point de ramassage",
        default=0.0
    )
    pickup_longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Longitude du point de ramassage",
        default=0.0
    )
    pickup_planned_time = models.DateTimeField(
        help_text="Heure de ramassage planifiée",
        null=True,
        blank=True
    )
    pickup_actual_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Heure de ramassage réelle"
    )
    pickup_notes = models.TextField(
        blank=True,
        help_text="Notes pour le ramassage"
    )
    
    # Nouveau : Informations de livraison (DELIVERY/DROPOFF)
    delivery_company = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nom de la compagnie à la livraison"
    )
    delivery_contact = models.CharField(
        max_length=100,
        blank=True,
        help_text="Contact à la livraison"
    )
    delivery_address = models.CharField(
        max_length=300,
        help_text="Adresse de livraison",
        default="Non spécifié"
    )
    delivery_latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Latitude du point de livraison",
        default=0.0
    )
    delivery_longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6,
        help_text="Longitude du point de livraison",
        default=0.0
    )
    delivery_planned_time = models.DateTimeField(
        help_text="Heure de livraison planifiée",
        null=True,
        blank=True
    )
    delivery_actual_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Heure de livraison réelle"
    )
    delivery_notes = models.TextField(
        blank=True,
        help_text="Notes pour la livraison"
    )
    
    # Signature de preuve de livraison
    delivery_signature = models.TextField(
        blank=True,
        help_text="Signature électronique du destinataire"
    )
    delivery_photo = models.ImageField(
        upload_to='trips/delivery_photos/',
        null=True,
        blank=True,
        help_text="Photo de la livraison"
    )
    
    # Informations sur le colis/cargaison
    cargo_description = models.CharField(
        max_length=300,
        help_text="Description du colis/cargaison à transporter",
        default="Non spécifié"
    )
    cargo_weight_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Poids de la cargaison en kilogrammes"
    )
    cargo_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Valeur déclarée de la cargaison"
    )
    cargo_special_instructions = models.TextField(
        blank=True,
        help_text="Instructions spéciales pour la cargaison (fragile, réfrigéré, etc.)"
    )
    
    # Documents et références
    reference_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Numéro de référence client"
    )
    bill_of_lading = models.CharField(
        max_length=50,
        blank=True,
        help_text="Numéro de connaissement"
    )
    shipping_documents = models.JSONField(
        default=list,
        help_text="Liste des documents de transport"
    )
    
    # Timing et distances
    planned_departure = models.DateTimeField(
        help_text="Heure de départ planifiée",
        default=timezone.now
    )
    planned_arrival = models.DateTimeField(
        help_text="Heure d'arrivée planifiée",
        default=timezone.now
    )
    actual_departure = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Heure de départ réelle"
    )
    actual_arrival = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Heure d'arrivée réelle"
    )
    
    estimated_distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance estimée en kilomètres"
    )
    actual_distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distance réelle parcourue en kilomètres"
    )
    estimated_duration_minutes = models.IntegerField(
        null=True,
        blank=True,
        help_text="Durée estimée en minutes"
    )
    
    # Position actuelle pendant le voyage
    current_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Position actuelle - latitude"
    )
    current_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Position actuelle - longitude"
    )
    last_position_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Dernière mise à jour de position"
    )
    
    # Données de route et navigation
    route_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Données de route calculées (polyline, instructions, etc.)"
    )
    
    # Chemin réellement suivi (mis à jour pendant le voyage)
    actual_route_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Chemin réellement suivi pendant le voyage (points GPS collectés)"
    )
    actual_route_points = models.JSONField(
        default=list,
        help_text="Liste des points GPS du chemin réellement parcouru [[lat, lng, timestamp], ...]"
    )
    
    # Statut et informations de voyage
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='PLANNED',
        help_text="Statut actuel du voyage"
    )
    
    # Informations client
    customer_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nom du client"
    )
    customer_contact = models.CharField(
        max_length=100,
        blank=True,
        help_text="Contact du client (téléphone/email)"
    )
    
    # Notes et commentaires
    driver_notes = models.TextField(
        blank=True,
        help_text="Notes du conducteur sur le voyage"
    )
    internal_notes = models.TextField(
        blank=True,
        help_text="Notes internes (non visibles par le conducteur)"
    )
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trips_created',
        help_text="Utilisateur qui a créé ce voyage"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trips_updated',
        help_text="Dernier utilisateur qui a modifié ce voyage"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-planned_departure']
        indexes = [
            models.Index(fields=['driver', 'status']),
            models.Index(fields=['vehicle', 'status']),
            models.Index(fields=['planned_departure']),
            models.Index(fields=['status']),
            models.Index(fields=['trip_number']),
        ]
    
    def __str__(self):
        return f"{self.trip_number} - {self.cargo_description[:50]}"
    
    def save(self, *args, **kwargs):
        # Générer automatiquement un numéro de voyage si non fourni
        if not self.trip_number:
            from django.utils import timezone
            today = timezone.now().strftime('%Y%m%d')
            last_trip = Trip.objects.filter(
                trip_number__startswith=f'TR{today}'
            ).order_by('trip_number').last()
            
            if last_trip:
                last_number = int(last_trip.trip_number[-3:])
                new_number = f'TR{today}{last_number + 1:03d}'
            else:
                new_number = f'TR{today}001'
                
            self.trip_number = new_number
        
        super().save(*args, **kwargs)
    
    @property
    def is_active(self):
        """Vérifie si le voyage est actuellement actif"""
        return self.status in ['PLANNED', 'IN_PROGRESS']
    
    @property
    def is_in_progress(self):
        """Vérifie si le voyage est en cours"""
        return self.status == 'IN_PROGRESS'
    
    @property
    def duration_hours(self):
        """Calcule la durée du voyage en heures"""
        if self.actual_departure and self.actual_arrival:
            delta = self.actual_arrival - self.actual_departure
            return delta.total_seconds() / 3600
        elif self.planned_departure and self.planned_arrival:
            delta = self.planned_arrival - self.planned_departure
            return delta.total_seconds() / 3600
        return 0
    
    @property
    def progress_percentage(self):
        """Calcule le pourcentage de progression du voyage"""
        if self.status == 'COMPLETED':
            return 100
        elif self.status == 'CANCELLED':
            return 0
        elif self.status == 'PLANNED':
            return 0
        else:  # IN_PROGRESS
            # Calcul basé sur la distance ou le temps
            if self.estimated_distance_km and self.actual_distance_km:
                return min(100, (float(self.actual_distance_km) / float(self.estimated_distance_km)) * 100)
            return 0
    
    def can_be_started(self):
        """Vérifie si le voyage peut être démarré"""
        if self.status != 'PLANNED':
            return False, f"Le voyage est déjà {self.get_status_display().lower()}"
        
        if not self.vehicle:
            return False, "Aucun véhicule assigné"
        
        if not self.vehicle.can_start_trip:
            return False, f"Le véhicule {self.vehicle.vehicle_number} ne peut pas démarrer de voyage"
        
        # Vérifier si le conducteur n'a pas d'autre voyage en cours
        active_trips = Trip.objects.filter(
            driver=self.driver,
            status='IN_PROGRESS'
        ).exclude(id=self.id)
        
        if active_trips.exists():
            return False, "Le conducteur a déjà un voyage en cours"
        
        return True, "Le voyage peut être démarré"
    
    def start_trip(self, current_latitude=None, current_longitude=None):
        """Démarre le voyage"""
        can_start, reason = self.can_be_started()
        if not can_start:
            raise ValueError(reason)
        
        self.status = 'IN_PROGRESS'
        self.actual_departure = timezone.now()
        
        if current_latitude and current_longitude:
            self.current_latitude = current_latitude
            self.current_longitude = current_longitude
            self.last_position_update = timezone.now()
        
        # Mettre à jour le statut du véhicule
        if self.vehicle:
            self.vehicle.operational_status = 'IN_USE'
            self.vehicle.save()
        
        self.save()
    
    def complete_trip(self, final_latitude=None, final_longitude=None):
        """Termine le voyage"""
        if self.status != 'IN_PROGRESS':
            raise ValueError("Seuls les voyages en cours peuvent être terminés")
        
        self.status = 'COMPLETED'
        self.actual_arrival = timezone.now()
        
        if final_latitude and final_longitude:
            self.current_latitude = final_latitude
            self.current_longitude = final_longitude
            self.last_position_update = timezone.now()
        
        # Mettre à jour le statut du véhicule
        if self.vehicle:
            self.vehicle.operational_status = 'AVAILABLE'
            self.vehicle.save()
        
        self.save()
    
    def cancel_trip(self, reason=""):
        """Annule le voyage"""
        if self.status == 'COMPLETED':
            raise ValueError("Un voyage terminé ne peut pas être annulé")
        
        old_status = self.status
        self.status = 'CANCELLED'
        
        if reason:
            self.internal_notes = f"{self.internal_notes}\n\nAnnulation: {reason}".strip()
        
        # Si le voyage était en cours, libérer le véhicule
        if old_status == 'IN_PROGRESS' and self.vehicle:
            self.vehicle.operational_status = 'AVAILABLE'
            self.vehicle.save()
        
        self.save()
    
    def update_position(self, latitude, longitude):
        """Met à jour la position actuelle du voyage"""
        if self.status != 'IN_PROGRESS':
            raise ValueError("La position ne peut être mise à jour que pour les voyages en cours")
        
        self.current_latitude = latitude
        self.current_longitude = longitude
        self.last_position_update = timezone.now()
        
        # Aussi mettre à jour la position du véhicule
        if self.vehicle:
            self.vehicle.current_latitude = latitude
            self.vehicle.current_longitude = longitude
            self.vehicle.last_location_update = timezone.now()
            self.vehicle.save()
        
        self.save()
    
    def get_distance_remaining(self):
        """Calcule la distance restante vers la destination"""
        if not (self.current_latitude and self.current_longitude):
            return self.estimated_distance_km
        
        # Ici on pourrait utiliser une API de calcul de distance
        # Pour l'instant, calcul direct à vol d'oiseau
        from math import radians, cos, sin, asin, sqrt
        
        def haversine(lon1, lat1, lon2, lat2):
            # Convertir en radians
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
            
            # Formule haversine
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            r = 6371  # Rayon de la Terre en kilomètres
            return c * r
        
        return haversine(
            float(self.current_longitude),
            float(self.current_latitude),
            float(self.destination_longitude),
            float(self.destination_latitude)
        )

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
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rest_stops_created',
        help_text="Utilisateur qui a créé cet arrêt"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rest_stops_updated',
        help_text="Dernier utilisateur qui a modifié cet arrêt"
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
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waypoints_created',
        help_text="Utilisateur qui a créé ce point de passage"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waypoints_updated',
        help_text="Dernier utilisateur qui a modifié ce point de passage"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['trip', 'sequence_order']
        unique_together = ['trip', 'sequence_order']
    
    def __str__(self):
        return f"{self.name} (#{self.sequence_order})"
