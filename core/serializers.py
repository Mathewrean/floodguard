from rest_framework import serializers
from rest_framework_gis.serializers import GeometryField
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from .models import AlertZone, FloodReading, IncidentReport, AlertLog


class AlertZoneSerializer(serializers.ModelSerializer):
    polygon = GeometryField()

    class Meta:
        model = AlertZone
        fields = '__all__'


class FloodReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FloodReading
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.location:
            data['location'] = [instance.location.x, instance.location.y]
        return data


class IncidentReportSerializer(serializers.ModelSerializer):
    location = GeometryField()
    photo = serializers.ImageField(write_only=True, required=False, allow_null=True)
    # Validate photo: max 5MB, dimensions max 2000x2000
    def validate_photo(self, value):
        max_size = 5 * 1024 * 1024  # 5MB
        if value.size > max_size:
            raise serializers.ValidationError(f"Photo size must be under {max_size/(1024*1024)}MB")
        
        # Check dimensions if PIL available
        try:
            from PIL import Image
            img = Image.open(value)
            if img.width > 2000 or img.height > 2000:
                raise serializers.ValidationError("Image dimensions must be under 2000x2000 pixels")
        except ImportError:
            pass  # Skip if PIL not available
        except Exception:
            raise serializers.ValidationError("Invalid image file")
        
        return value

    class Meta:
        model = IncidentReport
        fields = '__all__'

    def validate_location(self, value):
        # Validate location is within supported region (Kenya/East Africa bounds)
        lon = value.x
        lat = value.y
        # Kenya approximate bounds: longitude 33.0 to 42.0, latitude -5.0 to 5.0
        if not (33.0 <= lon <= 42.0 and -5.0 <= lat <= 5.0):
            raise serializers.ValidationError("Location outside supported area")
        return value


class AlertLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertLog
        fields = '__all__'
