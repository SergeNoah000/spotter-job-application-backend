from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, Company, UserProfile

class CompanySerializer(serializers.ModelSerializer):
    """Serializer pour les entreprises"""
    
    users_count = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True)
    
    class Meta:
        model = Company
        fields = [
            'id', 'name', 'address', 'dot_number', 'phone', 'email',
            'operation_schedule', 'logo', 'is_active', 'users_count',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'users_count', 'created_by', 'created_by_name', 
            'updated_by', 'updated_by_name', 'created_at', 'updated_at'
        ]
    
    def get_users_count(self, obj):
        return obj.users.filter(is_active=True).count()

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer pour les profils utilisateurs"""
    
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'license_expiry_date', 'medical_cert_expiry', 'hazmat_endorsement',
            'preferred_timezone', 'notification_email', 'notification_sms',
            'total_trips', 'total_miles',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'total_trips', 'total_miles', 'created_by', 'created_by_name', 
            'updated_by', 'updated_by_name', 'created_at', 'updated_at'
        ]

class UserSerializer(serializers.ModelSerializer):
    """Serializer pour les utilisateurs"""
    
    company_name = serializers.CharField(source='company.name', read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True)
    
    # Informations véhicule pour les conducteurs
    assigned_vehicle_info = serializers.SerializerMethodField()
    vehicle_status = serializers.ReadOnlyField()
    vehicle_location = serializers.ReadOnlyField()
    has_assigned_vehicle = serializers.ReadOnlyField()
    can_start_trip = serializers.ReadOnlyField()
    has_active_trip = serializers.ReadOnlyField()
    current_hos_hours = serializers.SerializerMethodField()
    available_driving_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'user_type', 'phone_number', 'cdl_number', 'company', 'company_name',
            'avatar', 'profile_image', 'date_of_birth', 'emergency_contact_name', 'emergency_contact_phone',
            'is_verified', 'is_active', 'must_change_password', 'date_joined',
            # Champs véhicule pour conducteurs
            'assigned_vehicle_info', 'vehicle_status', 'vehicle_location',
            'has_assigned_vehicle', 'can_start_trip', 'has_active_trip',
            'current_hos_hours', 'available_driving_hours',
            # Champs d'audit
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'full_name', 'company_name', 'date_joined',
            'assigned_vehicle_info', 'vehicle_status', 'vehicle_location',
            'has_assigned_vehicle', 'can_start_trip', 'has_active_trip',
            'current_hos_hours', 'available_driving_hours',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def get_assigned_vehicle_info(self, obj):
        """Retourne les informations du véhicule assigné pour les conducteurs"""
        if obj.is_driver() and obj.has_assigned_vehicle:
            vehicle = obj.assigned_vehicle
            return {
                'id': str(vehicle.id),
                'vehicle_number': vehicle.vehicle_number,
                'make': vehicle.make,
                'model': vehicle.model,
                'year': vehicle.year,
                'operational_status': vehicle.operational_status,
                'current_location': vehicle.current_location_display,
                'last_location_update': vehicle.last_location_update,
                'can_start_trip': vehicle.can_start_trip
            }
        return None
    
    def get_current_hos_hours(self, obj):
        """Retourne les heures HOS actuelles"""
        if obj.is_driver():
            return obj.get_current_hos_hours()
        return None
    
    def get_available_driving_hours(self, obj):
        """Retourne les heures de conduite disponibles"""
        if obj.is_driver():
            return obj.get_available_driving_hours()
        return None

class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer pour la création d'utilisateurs"""
    
    password = serializers.CharField(write_only=True, min_length=8, required=False)
    password_confirm = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'first_name', 'last_name',
            'user_type', 'phone_number', 'cdl_number', 'avatar', 'profile_image',
            'date_of_birth', 'emergency_contact_name', 'emergency_contact_phone'
        ]
        # Retrait du champ 'company' qui sera assigné automatiquement
    
    def validate(self, attrs):
        # Password et password_confirm sont optionnels car un mot de passe temporaire sera généré
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise serializers.ValidationError("Passwords don't match")
        
        return attrs
    
    def create(self, validated_data):
        # Retirer password_confirm s'il existe
        validated_data.pop('password_confirm', None)
        password = validated_data.pop('password', None)
        
        user = User.objects.create_user(**validated_data)
        
        # Si un mot de passe est fourni, l'utiliser
        if password:
            user.set_password(password)
            user.must_change_password = False
        else:
            # Sinon, forcer le changement de mot de passe
            user.must_change_password = True
        
        user.save()
        
        # Create user profile
        UserProfile.objects.create(user=user)
        
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour la mise à jour d'utilisateurs"""
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'cdl_number',
            'avatar', 'profile_image', 'date_of_birth', 'emergency_contact_name', 
            'emergency_contact_phone'
        ]

class LoginSerializer(serializers.Serializer):
    """Serializer pour l'authentification"""
    
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(
                request=self.context.get('request'),
                username=email,
                password=password
            )
            
            if not user:
                raise serializers.ValidationError('Invalid email or password')
            
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Must include email and password')

class ChangePasswordSerializer(serializers.Serializer):
    """Serializer pour changer le mot de passe"""
    
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords don't match")
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value

class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer pour demander une réinitialisation de mot de passe"""
    
    email = serializers.EmailField()

class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer pour confirmer la réinitialisation de mot de passe"""
    
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8)
    new_password_confirm = serializers.CharField()
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs