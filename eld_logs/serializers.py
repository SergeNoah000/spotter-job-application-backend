from rest_framework import serializers
from .models import ELDLog, HOSViolation, ELDExport
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