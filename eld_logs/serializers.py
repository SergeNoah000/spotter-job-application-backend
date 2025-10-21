from rest_framework import serializers
from .models import ELDLog, HOSViolation, ELDExport, DutyStatusEntry
from accounts.serializers import UserSerializer
from trips.serializers import VehicleSerializer

class ELDLogSerializer(serializers.ModelSerializer):
    """Serializer pour les logs ELD"""
    
    driver_name = serializers.CharField(source='driver.get_full_name', read_only=True)
    vehicle_number = serializers.CharField(source='vehicle.vehicle_number', read_only=True)
    duration_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = ELDLog
        fields = [
            'id', 'driver', 'driver_name', 'vehicle', 'vehicle_number',
            'log_date', 'duty_status', 'start_time', 'end_time',
            'location', 'odometer_reading', 'engine_hours',
            'notes', 'duration_hours', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'driver_name', 'vehicle_number', 'duration_hours', 'created_at', 'updated_at']
    
    def get_duration_hours(self, obj):
        """Calculer la durée en heures"""
        if obj.end_time and obj.start_time:
            duration = obj.end_time - obj.start_time
            return round(duration.total_seconds() / 3600, 2)
        return None

class ELDLogCreateSerializer(serializers.ModelSerializer):
    """Serializer pour la création de logs ELD"""
    
    class Meta:
        model = ELDLog
        fields = [
            'driver', 'vehicle', 'log_date', 'duty_status',
            'start_time', 'end_time', 'location', 'odometer_reading',
            'engine_hours', 'notes'
        ]
        extra_kwargs = {
            'driver': {'required': False, 'allow_null': True},
            'vehicle': {'required': False, 'allow_null': True}
        }
    
    def validate_duty_status(self, value):
        valid_statuses = ['off_duty', 'sleeper_berth', 'driving', 'on_duty_not_driving']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Invalid duty status. Must be one of: {valid_statuses}")
        return value

class DutyStatusEntrySerializer(serializers.ModelSerializer):
    """Serializer pour les entrées de statut de service (segments)"""
    
    trip_id = serializers.UUIDField(source='trip.id', read_only=True, allow_null=True)
    trip_origin = serializers.CharField(source='trip.origin', read_only=True, allow_null=True)
    trip_destination = serializers.CharField(source='trip.destination', read_only=True, allow_null=True)
    duration_hours = serializers.SerializerMethodField()
    
    class Meta:
        model = DutyStatusEntry
        fields = [
            'id', 'eld_log', 'trip', 'trip_id', 'trip_origin', 'trip_destination',
            'start_time', 'end_time', 'status', 'location', 
            'latitude', 'longitude', 'remarks', 'odometer_reading',
            'duration_hours', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'duration_hours']
        extra_kwargs = {
            'trip': {'required': False, 'allow_null': True},
            'eld_log': {'required': True},
            'end_time': {'required': False, 'allow_null': True}
        }
    
    def get_duration_hours(self, obj):
        """Calculer la durée en heures"""
        if obj.end_time and obj.start_time:
            duration = obj.end_time - obj.start_time
            return round(duration.total_seconds() / 3600, 2)
        elif obj.start_time and not obj.end_time:
            # Segment actif - calculer depuis maintenant
            from datetime import datetime
            duration = datetime.now() - obj.start_time
            return round(duration.total_seconds() / 3600, 2)
        return 0
    
    def validate_status(self, value):
        """Valider le statut"""
        valid_statuses = ['OFF_DUTY', 'SLEEPER_BERTH', 'DRIVING', 'ON_DUTY_NOT_DRIVING']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Invalid status. Must be one of: {valid_statuses}")
        return value


class DutyStatusEntryCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer des entrées de statut"""
    
    class Meta:
        model = DutyStatusEntry
        fields = [
            'eld_log', 'trip', 'status', 'location', 
            'latitude', 'longitude', 'remarks', 'odometer_reading'
        ]
        extra_kwargs = {
            'trip': {'required': False, 'allow_null': True},
            'location': {'required': False},
            'latitude': {'required': False, 'allow_null': True},
            'longitude': {'required': False, 'allow_null': True},
            'remarks': {'required': False},
            'odometer_reading': {'required': False, 'allow_null': True}
        }


class HOSViolationSerializer(serializers.ModelSerializer):
    """Serializer pour les violations HOS"""
    
    eld_log_date = serializers.DateField(source='eld_log.log_date', read_only=True)
    driver_name = serializers.CharField(source='eld_log.driver.get_full_name', read_only=True)
    
    class Meta:
        model = HOSViolation
        fields = [
            'id', 'eld_log', 'eld_log_date', 'driver_name',
            'violation_type', 'description', 'severity',
            'detected_at', 'resolved', 'resolved_at',
            'resolution_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'detected_at', 'created_at', 'updated_at', 'eld_log_date', 'driver_name']


class ELDExportSerializer(serializers.ModelSerializer):
    """Serializer pour les exports ELD"""
    
    driver_name = serializers.CharField(source='driver.get_full_name', read_only=True)
    
    class Meta:
        model = ELDExport
        fields = [
            'id', 'driver', 'driver_name', 'start_date', 'end_date',
            'export_format', 'file_path', 'file_size',
            'created_at', 'exported_by'
        ]
        read_only_fields = ['id', 'file_path', 'file_size', 'created_at', 'driver_name']