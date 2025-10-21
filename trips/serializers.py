from rest_framework import serializers
from .models import Vehicle, Trip, RestStop, TripWaypoint, VehicleAssignment, TripSegment
from accounts.serializers import UserSerializer

class VehicleAssignmentSerializer(serializers.ModelSerializer):
    """Serializer pour l'historique des attributions de véhicules"""
    
    driver_name = serializers.CharField(source='driver.get_full_name', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)
    ended_by_name = serializers.CharField(source='ended_by.get_full_name', read_only=True)
    duration_display = serializers.SerializerMethodField()
    
    class Meta:
        model = VehicleAssignment
        fields = [
            'id', 'driver', 'driver_name', 'start_date', 'end_date',
            'assigned_by', 'assigned_by_name', 'ended_by', 'ended_by_name',
            'notes', 'end_reason', 'is_active', 'duration_display',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'driver_name', 'assigned_by_name', 'ended_by_name',
            'is_active', 'duration_display', 'created_at', 'updated_at'
        ]
    
    def get_duration_display(self, obj):
        """Affichage formaté de la durée"""
        duration = obj.duration
        days = duration.days
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}j {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

class VehicleAssignmentCreateSerializer(serializers.Serializer):
    """Serializer pour créer une attribution de véhicule"""
    
    driver_id = serializers.UUIDField()
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    
    def validate_driver_id(self, value):
        """Valide que le conducteur existe et est actif"""
        from accounts.models import User
        try:
            driver = User.objects.get(id=value, user_type='DRIVER', is_active=True)
            return driver
        except User.DoesNotExist:
            raise serializers.ValidationError("Conducteur non trouvé ou inactif")
    
    def validate(self, attrs):
        """Validation globale de l'attribution"""
        request = self.context.get('request')
        vehicle = self.context.get('vehicle')
        driver = attrs['driver_id']
        
        if not vehicle:
            raise serializers.ValidationError("Véhicule non spécifié")
        
        # Vérifier les permissions
        if request and hasattr(request.user, 'company'):
            if driver.company != request.user.company:
                raise serializers.ValidationError("Le conducteur doit appartenir à la même entreprise")
        
        # Vérifier si l'attribution est possible
        can_assign, reason = vehicle.can_be_assigned_to(driver)
        if not can_assign:
            raise serializers.ValidationError(f"Attribution impossible: {reason}")
        
        return attrs

class VehicleUnassignSerializer(serializers.Serializer):
    """Serializer pour retirer l'attribution d'un véhicule"""
    
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)

class VehicleSerializer(serializers.ModelSerializer):
    """Serializer pour les véhicules"""
    
    company_name = serializers.CharField(source='company.name', read_only=True)
    current_driver_name = serializers.SerializerMethodField()
    current_driver_info = serializers.SerializerMethodField()
    current_assignment = serializers.SerializerMethodField()
    assignment_history = serializers.SerializerMethodField()
    can_be_assigned_to_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Vehicle
        fields = [
            'id', 'vehicle_number', 'make', 'model', 'year', 'vin',
            'license_plate', 'vehicle_type', 'company', 'company_name',
            'current_driver', 'current_driver_name', 'current_driver_info',
            'last_assignment_date', 'current_assignment', 'assignment_history',
            'operational_status', 'current_latitude', 'current_longitude',
            'current_location_display', 'last_location_update',
            'front_image', 'side_image', 'rear_image',
            'is_active', 'is_assigned', 'can_start_trip', 'can_be_assigned_to_info',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'company', 'company_name', 'current_driver_name', 'current_driver_info',
            'last_assignment_date', 'current_assignment', 'assignment_history',
            'current_location_display', 'is_assigned', 'can_start_trip',
            'can_be_assigned_to_info', 'created_at', 'updated_at'
        ]
    
    def create(self, validated_data):
        """Créer un véhicule avec la compagnie de l'utilisateur connecté"""
        request = self.context.get('request')
        if request and hasattr(request.user, 'company') and request.user.company:
            validated_data['company'] = request.user.company
        else:
            raise serializers.ValidationError({
                'company': 'Impossible de déterminer la compagnie de l\'utilisateur.'
            })
        
        return super().create(validated_data)

    def validate_vehicle_number(self, value):
        """Valider l'unicité du numéro de véhicule dans la compagnie"""
        request = self.context.get('request')
        if request and hasattr(request.user, 'company'):
            # Vérifier l'unicité du numéro de véhicule dans la compagnie
            qs = Vehicle.objects.filter(
                vehicle_number=value,
                company=request.user.company
            )
            
            # Exclure l'instance actuelle lors de la mise à jour
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            
            if qs.exists():
                raise serializers.ValidationError(
                    f"Un véhicule avec le numéro '{value}' existe déjà dans votre entreprise."
                )
        
        return value

    def validate_vin(self, value):
        """Valider l'unicité du VIN"""
        qs = Vehicle.objects.filter(vin=value)
        
        # Exclure l'instance actuelle lors de la mise à jour
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise serializers.ValidationError(
                f"Un véhicule avec le VIN '{value}' existe déjà."
            )
        
        return value

    def validate_license_plate(self, value):
        """Valider l'unicité de la plaque d'immatriculation"""
        qs = Vehicle.objects.filter(license_plate=value)
        
        # Exclure l'instance actuelle lors de la mise à jour
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise serializers.ValidationError(
                f"Un véhicule avec la plaque '{value}' existe déjà."
            )
        
        return value
    
    def get_current_driver_name(self, obj):
        """Retourne le nom du conducteur actuellement assigné"""
        if obj.current_driver:
            return obj.current_driver.get_full_name()
        return None
    
    def get_current_driver_info(self, obj):
        """Retourne les infos détaillées du conducteur actuellement assigné"""
        if obj.current_driver:
            driver = obj.current_driver
            return {
                'id': str(driver.id),
                'name': driver.get_full_name(),
                'email': driver.email,
                'phone': getattr(driver, 'phone_number', ''),
                'cdl_number': getattr(driver, 'cdl_number', ''),
                'user_type': driver.user_type
            }
        return None
    
    def get_current_assignment(self, obj):
        """Retourne l'attribution actuelle"""
        assignment = obj.get_current_assignment()
        if assignment:
            return VehicleAssignmentSerializer(assignment).data
        return None
    
    def get_assignment_history(self, obj):
        """Retourne l'historique des attributions (5 dernières)"""
        history = obj.get_assignment_history(limit=5)
        return VehicleAssignmentSerializer(history, many=True).data
    
    def get_can_be_assigned_to_info(self, obj):
        """Infos sur la possibilité d'attribution pour différents conducteurs"""
        request = self.context.get('request')
        if not request or not hasattr(request.user, 'company'):
            return {}
        
        # Récupérer les conducteurs de la même entreprise
        from accounts.models import User
        drivers = User.objects.filter(
            user_type='DRIVER',
            company=request.user.company,
            is_active=True
        ).exclude(id=obj.current_driver_id if obj.current_driver else None)
        
        assignment_info = {}
        for driver in drivers[:10]:  # Limiter à 10 pour éviter la surcharge
            can_assign, reason = obj.can_be_assigned_to(driver)
            assignment_info[str(driver.id)] = {
                'name': driver.get_full_name(),
                'can_assign': can_assign,
                'reason': reason
            }
        
        return assignment_info

class RestStopSerializer(serializers.ModelSerializer):
    """Serializer pour les arrêts de repos"""
    
    duration_hours = serializers.ReadOnlyField()
    
    class Meta:
        model = RestStop
        fields = [
            'id', 'location', 'latitude', 'longitude', 'address',
            'stop_type', 'planned_start_time', 'planned_duration',
            'actual_start_time', 'actual_duration', 'is_mandatory',
            'is_completed', 'notes', 'fuel_gallons', 'duration_hours',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'duration_hours', 'created_at', 'updated_at']

class TripWaypointSerializer(serializers.ModelSerializer):
    """Serializer pour les points de passage"""
    
    class Meta:
        model = TripWaypoint
        fields = [
            'id', 'name', 'latitude', 'longitude', 'sequence_order',
            'estimated_arrival', 'actual_arrival', 'distance_from_previous',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class TripSegmentSerializer(serializers.ModelSerializer):
    """Serializer pour les segments de voyage (ramassage/livraison)"""
    
    segment_type_display = serializers.CharField(source='get_segment_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    trip_number = serializers.CharField(source='trip.trip_number', read_only=True)
    trip_title = serializers.CharField(source='trip.title', read_only=True)
    duration_minutes = serializers.ReadOnlyField()
    is_completed = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True, allow_null=True)
    
    class Meta:
        model = TripSegment
        fields = [
            'id', 'trip', 'trip_number', 'trip_title', 'sequence_order',
            'segment_type', 'segment_type_display',
            'location_name', 'address', 'latitude', 'longitude',
            'contact_name', 'contact_phone',
            'cargo_description', 'cargo_weight_kg', 'cargo_quantity',
            'reference_number', 'proof_of_delivery',
            'planned_time', 'actual_arrival_time', 'actual_departure_time',
            'distance_from_previous_km',
            'status', 'status_display',
            'special_instructions', 'driver_notes',
            'signature_data', 'signed_by_name', 'signed_at',
            'duration_minutes', 'is_completed',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'trip_number', 'trip_title', 'actual_arrival_time', 'actual_departure_time',
            'signed_at', 'duration_minutes', 'is_completed',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
    
    def validate(self, data):
        """Validation des données du segment"""
        # Valider les coordonnées
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if latitude and abs(latitude) > 90:
            raise serializers.ValidationError({
                'latitude': "La latitude doit être entre -90 et 90"
            })
        
        if longitude and abs(longitude) > 180:
            raise serializers.ValidationError({
                'longitude': "La longitude doit être entre -180 et 180"
            })
        
        return data


class TripSegmentCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer un segment de voyage"""
    
    class Meta:
        model = TripSegment
        fields = [
            'trip', 'sequence_order', 'segment_type',
            'location_name', 'address', 'latitude', 'longitude',
            'contact_name', 'contact_phone',
            'cargo_description', 'cargo_weight_kg', 'cargo_quantity',
            'reference_number', 'planned_time',
            'distance_from_previous_km', 'special_instructions'
        ]
    
    def create(self, validated_data):
        """Créer le segment avec l'utilisateur qui crée"""
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)


class TripSegmentUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour mettre à jour un segment"""
    
    class Meta:
        model = TripSegment
        fields = [
            'location_name', 'address', 'latitude', 'longitude',
            'contact_name', 'contact_phone',
            'cargo_description', 'cargo_weight_kg', 'cargo_quantity',
            'reference_number', 'planned_time',
            'distance_from_previous_km', 'special_instructions',
            'driver_notes', 'proof_of_delivery'
        ]
    
    def update(self, instance, validated_data):
        """Mise à jour avec traçage de l'utilisateur"""
        request = self.context.get('request')
        if request and request.user:
            validated_data['updated_by'] = request.user
        
        return super().update(instance, validated_data)


class TripSegmentStartSerializer(serializers.Serializer):
    """Serializer pour démarrer un segment"""
    
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)


class TripSegmentCompleteSerializer(serializers.Serializer):
    """Serializer pour terminer un segment"""
    
    signature_data = serializers.CharField(required=False, allow_blank=True)
    signed_by_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    proof_of_delivery = serializers.ImageField(required=False)
    driver_notes = serializers.CharField(required=False, allow_blank=True)

class TripSerializer(serializers.ModelSerializer):
    """Serializer complet pour les voyages"""
    
    driver_name = serializers.CharField(source='driver.get_full_name', read_only=True)
    driver_info = serializers.SerializerMethodField()
    vehicle_name = serializers.CharField(source='vehicle.vehicle_number', read_only=True, allow_null=True)
    vehicle_info = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    progress_percentage = serializers.ReadOnlyField()
    duration_hours = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    is_in_progress = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True, allow_null=True)
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True, allow_null=True)
    
    # Exposer les alias pour la compatibilité
    origin = serializers.CharField(source='origin_address', read_only=True)
    destination = serializers.CharField(source='destination_address', read_only=True)
    origin_lat = serializers.DecimalField(source='origin_latitude', max_digits=9, decimal_places=6, read_only=True)
    origin_lng = serializers.DecimalField(source='origin_longitude', max_digits=9, decimal_places=6, read_only=True)
    destination_lat = serializers.DecimalField(source='destination_latitude', max_digits=9, decimal_places=6, read_only=True)
    destination_lng = serializers.DecimalField(source='destination_longitude', max_digits=9, decimal_places=6, read_only=True)
    manager_notes = serializers.CharField(source='internal_notes', allow_blank=True, required=False)
    
    class Meta:
        model = Trip
        fields = [
            'id', 'trip_number', 'title', 'description', 'cargo_description',
            'driver', 'driver_name', 'driver_info',
            'vehicle', 'vehicle_name', 'vehicle_info',
            'origin_address', 'origin_latitude', 'origin_longitude', 'origin_notes',
            'destination_address', 'destination_latitude', 'destination_longitude', 'destination_notes',
            'origin', 'destination', 'origin_lat', 'origin_lng', 'destination_lat', 'destination_lng',
            'cargo_weight_kg', 'cargo_value', 'cargo_special_instructions',
            'reference_number', 'bill_of_lading', 'shipping_documents',
            'planned_departure', 'planned_arrival', 'actual_departure', 'actual_arrival',
            'estimated_distance_km', 'actual_distance_km', 'estimated_duration_minutes',
            'current_latitude', 'current_longitude', 'last_position_update',
            'route_data', 'actual_route_data', 'actual_route_points',
            'status', 'status_display', 'priority', 'priority_display',
            'customer_name', 'customer_contact',
            'driver_notes', 'internal_notes', 'manager_notes',
            'progress_percentage', 'duration_hours', 'is_active', 'is_in_progress',
            'created_by', 'created_by_name', 'updated_by', 'updated_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'trip_number', 'actual_departure', 'actual_arrival', 'actual_distance_km',
            'current_latitude', 'current_longitude', 'last_position_update',
            'actual_route_data', 'actual_route_points',
            'created_by', 'updated_by', 'created_at', 'updated_at'
        ]
    
    def get_driver_info(self, obj):
        if obj.driver:
            return {
                'id': str(obj.driver.id),
                'name': obj.driver.get_full_name(),
                'email': obj.driver.email,
                'phone': obj.driver.phone_number,
                'cdl_number': getattr(obj.driver, 'cdl_number', None),
                'user_type': obj.driver.user_type
            }
        return None
    
    def get_vehicle_info(self, obj):
        if obj.vehicle:
            return {
                'id': str(obj.vehicle.id),
                'vehicle_number': obj.vehicle.vehicle_number,
                'make': obj.vehicle.make,
                'model': obj.vehicle.model,
                'license_plate': obj.vehicle.license_plate
            }
        return None


class TripCreateSerializer(serializers.ModelSerializer):
    """Serializer pour la création de voyages"""
    
    # Utiliser les noms attendus par le frontend mais mapper sur les vrais champs
    origin_address = serializers.CharField(max_length=300)
    origin_latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    origin_longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    destination_address = serializers.CharField(max_length=300)
    destination_latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    destination_longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    internal_notes = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = Trip
        fields = [
            'title', 'description', 'cargo_description',
            'driver', 'vehicle',
            'origin_address', 'origin_latitude', 'origin_longitude', 'origin_notes',
            'destination_address', 'destination_latitude', 'destination_longitude', 'destination_notes',
            'cargo_weight_kg', 'cargo_value', 'cargo_special_instructions',
            'reference_number', 'bill_of_lading',
            'planned_departure', 'planned_arrival',
            'estimated_distance_km', 'estimated_duration_minutes',
            'route_data',
            'priority', 'customer_name', 'customer_contact',
            'driver_notes', 'internal_notes'
        ]
    
    def validate(self, data):
        """Validation des données"""
        # Valider que le conducteur est bien un conducteur
        driver = data.get('driver')
        if driver and driver.user_type != 'DRIVER':
            raise serializers.ValidationError({
                'driver': "L'utilisateur sélectionné n'est pas un conducteur"
            })
        
        # Valider les coordonnées
        if abs(data.get('origin_latitude', 0)) > 90:
            raise serializers.ValidationError({
                'origin_latitude': "La latitude doit être entre -90 et 90"
            })
        
        if abs(data.get('origin_longitude', 0)) > 180:
            raise serializers.ValidationError({
                'origin_longitude': "La longitude doit être entre -180 et 180"
            })
        
        if abs(data.get('destination_latitude', 0)) > 90:
            raise serializers.ValidationError({
                'destination_latitude': "La latitude doit être entre -90 et 90"
            })
        
        if abs(data.get('destination_longitude', 0)) > 180:
            raise serializers.ValidationError({
                'destination_longitude': "La longitude doit être entre -180 et 180"
            })
        
        # Valider les dates
        planned_departure = data.get('planned_departure')
        planned_arrival = data.get('planned_arrival')
        
        if planned_arrival and planned_departure and planned_arrival <= planned_departure:
            raise serializers.ValidationError({
                'planned_arrival': "L'heure d'arrivée doit être postérieure au départ"
            })
        
        return data
    
    def create(self, validated_data):
        """Créer le voyage avec l'utilisateur qui crée"""
        request = self.context.get('request')
        if request and request.user:
            validated_data['created_by'] = request.user
        
        return super().create(validated_data)


class TripUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour la mise à jour de voyages"""
    
    origin_address = serializers.CharField(max_length=300, required=False)
    origin_latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    origin_longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    destination_address = serializers.CharField(max_length=300, required=False)
    destination_latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    destination_longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    internal_notes = serializers.CharField(required=False, allow_blank=True)
    
    class Meta:
        model = Trip
        fields = [
            'title', 'description', 'cargo_description',
            'vehicle',
            'origin_address', 'origin_latitude', 'origin_longitude', 'origin_notes',
            'destination_address', 'destination_latitude', 'destination_longitude', 'destination_notes',
            'cargo_weight_kg', 'cargo_value', 'cargo_special_instructions',
            'reference_number', 'bill_of_lading',
            'planned_departure', 'planned_arrival',
            'estimated_distance_km', 'estimated_duration_minutes',
            'route_data',
            'priority', 'customer_name', 'customer_contact',
            'driver_notes', 'internal_notes'
        ]
    
    def update(self, instance, validated_data):
        """Mise à jour avec traçage de l'utilisateur"""
        request = self.context.get('request')
        if request and request.user:
            validated_data['updated_by'] = request.user
        
        return super().update(instance, validated_data)

class TripPlanningSerializer(serializers.Serializer):
    """Serializer pour la planification automatique de voyages"""
    
    current_location = serializers.CharField(max_length=200)
    pickup_location = serializers.CharField(max_length=200)
    dropoff_location = serializers.CharField(max_length=200)
    current_cycle_hours = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=0, max_value=70)
    planned_start_time = serializers.DateTimeField()
    
    def validate_current_cycle_hours(self, value):
        if value >= 70:
            raise serializers.ValidationError("Cannot start trip with 70+ cycle hours used")
        return value

class RouteCalculationSerializer(serializers.Serializer):
    """Serializer pour le calcul d'itinéraires"""
    
    waypoints = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        min_length=2
    )
    optimize = serializers.BooleanField(default=True)
    vehicle_type = serializers.ChoiceField(
        choices=['TRACTOR', 'STRAIGHT_TRUCK', 'VAN'],
        default='TRACTOR'
    )
    
    def validate_waypoints(self, value):
        for waypoint in value:
            if 'lat' not in waypoint or 'lng' not in waypoint:
                raise serializers.ValidationError("Each waypoint must have 'lat' and 'lng' fields")
            try:
                float(waypoint['lat'])
                float(waypoint['lng'])
            except (ValueError, TypeError):
                raise serializers.ValidationError("Latitude and longitude must be valid numbers")
        return value