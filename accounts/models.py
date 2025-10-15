from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.validators import RegexValidator
import uuid

class Company(models.Model):
    """Modèle pour les entreprises de transport"""
    
    OPERATION_SCHEDULE_CHOICES = [
        ('7_DAY', '60h/7 jours'),
        ('8_DAY', '70h/8 jours'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    address = models.TextField()
    dot_number = models.CharField(
        max_length=10,
        validators=[RegexValidator(r'^\d+$', 'DOT number must contain only digits')]
    )
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    operation_schedule = models.CharField(
        max_length=10,
        choices=OPERATION_SCHEDULE_CHOICES,
        default='8_DAY'
    )
    logo = models.CharField(max_length=500, blank=True)  # Ajout selon conception
    is_active = models.BooleanField(default=True)
    
    # Champs d'audit
    created_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='companies_created',
        help_text="Utilisateur qui a créé cette entreprise"
    )
    updated_by = models.ForeignKey(
        'User', 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='companies_updated',
        help_text="Dernier utilisateur qui a modifié cette entreprise"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Companies"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} (DOT: {self.dot_number})"

class UserManager(BaseUserManager):
    """Manager personnalisé pour le modèle User"""
    
    def create_user(self, email, password=None, **extra_fields):
        """Créer un utilisateur normal"""
        if not email:
            raise ValueError('Email is required')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Créer un superutilisateur"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_type', 'ADMIN')
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    """Modèle utilisateur personnalisé pour l'application Spotter"""
    
    USER_TYPE_CHOICES = [
        ('ADMIN', 'Administrateur'),
        ('DRIVER', 'Conducteur'),
        ('FLEET_MANAGER', 'Gestionnaire de flotte'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    username = None  # Remove username field
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    
    user_type = models.CharField(
        max_length=15,
        choices=USER_TYPE_CHOICES,
        default='DRIVER'
    )
    
    phone_number = models.CharField(
        max_length=15,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Invalid phone number')]
    )
    
    cdl_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Commercial Driver's License Number"
    )
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,  # Permettre null temporairement
        blank=True  # Permettre blank dans les formulaires
    )
    
    # Profile fields
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    profile_image = models.CharField(max_length=500, blank=True)  # Ajout selon conception
    date_of_birth = models.DateField(blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True)
    
    # Status fields
    is_verified = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=True, help_text="Forcer le changement de mot de passe à la première connexion")
    email_verification_token = models.CharField(max_length=64, blank=True, null=True)
    password_reset_token = models.CharField(max_length=64, blank=True, null=True)
    password_reset_token_expires = models.DateTimeField(blank=True, null=True)
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    
    # Champs d'audit
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users_created',
        help_text="Utilisateur qui a créé ce compte"
    )
    updated_by = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users_updated',
        help_text="Dernier utilisateur qui a modifié ce compte"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['user_type']),
            models.Index(fields=['company']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_user_type_display()})"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def is_admin(self):
        return self.user_type == 'ADMIN'
    
    def is_driver(self):
        return self.user_type == 'DRIVER'
    
    def is_fleet_manager(self):
        return self.user_type == 'FLEET_MANAGER'
    
    @property
    def can_manage_users(self):
        return self.user_type in ['ADMIN', 'FLEET_MANAGER']
    
    @property
    def can_create_trips(self):
        return self.user_type in ['DRIVER', 'FLEET_MANAGER']
    
    # Propriétés liées aux véhicules (pour les conducteurs)
    @property
    def has_assigned_vehicle(self):
        """Vérifie si le conducteur a un véhicule assigné"""
        if self.is_driver():
            return hasattr(self, 'assigned_vehicle') and self.assigned_vehicle is not None
        return False
    
    @property
    def can_start_trip(self):
        """Vérifie si le conducteur peut commencer un voyage"""
        if not self.is_driver():
            return False
        
        # Le conducteur doit avoir un véhicule assigné et opérationnel
        if not self.has_assigned_vehicle:
            return False
            
        vehicle = self.assigned_vehicle
        return vehicle.can_start_trip
    
    @property
    def current_trip(self):
        """Retourne le voyage actuel du conducteur s'il y en a un"""
        if self.is_driver():
            return self.trips.filter(status='IN_PROGRESS').first()
        return None
    
    @property
    def has_active_trip(self):
        """Vérifie si le conducteur a un voyage en cours"""
        return self.current_trip is not None
    
    @property
    def vehicle_status(self):
        """Retourne le statut du véhicule assigné"""
        if self.has_assigned_vehicle:
            return self.assigned_vehicle.operational_status
        return None
    
    @property
    def vehicle_location(self):
        """Retourne la localisation actuelle du véhicule assigné"""
        if self.has_assigned_vehicle:
            return self.assigned_vehicle.current_location_display
        return "Aucun véhicule assigné"
    
    def get_current_hos_hours(self):
        """Calcule les heures HOS actuelles du conducteur"""
        if not self.is_driver():
            return 0
        
        try:
            # Calculer les heures HOS depuis les logs ELD
            from eld_logs.models import DutyStatusEntry
            from datetime import timedelta
            from django.utils import timezone
            
            # Calculer sur les 8 derniers jours (70h/8 jours)
            eight_days_ago = timezone.now() - timedelta(days=8)
            
            # Récupérer tous les statuts de conduite sur cette période
            # Le conducteur est accessible via eld_log__driver
            driving_entries = DutyStatusEntry.objects.filter(
                eld_log__driver=self,
                status='DRIVING',
                start_time__gte=eight_days_ago
            )
            
            total_hours = 0
            for entry in driving_entries:
                if entry.duration:
                    total_hours += entry.duration.total_seconds() / 3600
            
            return round(total_hours, 2)
        except Exception as e:
            # En cas d'erreur, retourner 0 pour ne pas bloquer l'authentification
            print(f"Erreur lors du calcul des heures HOS: {e}")
            return 0
    
    def get_available_driving_hours(self):
        """Calcule les heures de conduite disponibles"""
        if not self.is_driver():
            return 0
        
        # Récupérer le cycle de la compagnie (70h/8 jours par défaut)
        max_hours = 70
        if self.company and self.company.operation_schedule == '7_DAY':
            max_hours = 60
        
        used_hours = self.get_current_hos_hours()
        return max(0, round(max_hours - used_hours, 2))

class UserProfile(models.Model):
    """Profil étendu pour les utilisateurs"""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    
    # Driver specific fields
    license_expiry_date = models.DateField(blank=True, null=True)
    medical_cert_expiry = models.DateField(blank=True, null=True)
    hazmat_endorsement = models.BooleanField(default=False)
    
    # Preferences
    preferred_timezone = models.CharField(max_length=50, default='America/New_York')
    notification_email = models.BooleanField(default=True)
    notification_sms = models.BooleanField(default=False)
    
    # Statistics
    total_trips = models.IntegerField(default=0)
    total_miles = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Champs d'audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profiles_created',
        help_text="Utilisateur qui a créé ce profil"
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profiles_updated',
        help_text="Dernier utilisateur qui a modifié ce profil"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Profile of {self.user.get_full_name()}"
