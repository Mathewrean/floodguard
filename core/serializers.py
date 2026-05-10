from rest_framework import serializers
from rest_framework_gis.serializers import GeometryField
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.conf import settings
from .models import AlertZone, FloodReading, IncidentReport, AlertLog


class AlertZoneSerializer(serializers.ModelSerializer):
    polygon = GeometryField()
    centroid = serializers.SerializerMethodField()

    class Meta:
        model = AlertZone
        fields = [
            'id', 'name', 'polygon', 'centroid', 'risk_threshold', 'risk_score',
            'manual_override_active', 'manual_override_until', 'created_at', 'updated_at',
        ]

    def get_centroid(self, obj):
        if not obj.polygon:
            return None
        centroid = obj.polygon.centroid
        return [centroid.x, centroid.y]


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
    location = GeometryField(required=False)
    latitude = serializers.FloatField(write_only=True, required=False)
    longitude = serializers.FloatField(write_only=True, required=False)
    water_depth_cm = serializers.IntegerField(write_only=True, required=False)
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
        fields = [
            'id', 'location', 'latitude', 'longitude', 'severity', 'description',
            'water_depth_cm', 'photo', 'status', 'submitted_by', 'reviewed_by',
            'acknowledged_by', 'acknowledged_at', 'cluster_id', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'status', 'submitted_by', 'reviewed_by', 'acknowledged_by',
            'acknowledged_at', 'cluster_id', 'created_at', 'updated_at',
        ]

    def validate_location(self, value):
        # Validate location is within configured geographic bounds
        lon = value.x
        lat = value.y
        # Use configured bounds from settings (default: Kenya/East Africa)
        bounds = getattr(settings, 'DEFAULT_GEO_BOUNDS', [33.0, -5.0, 42.0, 5.0])
        if len(bounds) == 4:
            min_lon, min_lat, max_lon, max_lat = bounds
            if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
                raise serializers.ValidationError(
                    f"Location outside supported area (bounds: {bounds})"
                )
        return value

    def validate(self, attrs):
        latitude = attrs.pop('latitude', None)
        longitude = attrs.pop('longitude', None)
        attrs.pop('water_depth_cm', None)
        if not attrs.get('location') and latitude is not None and longitude is not None:
            attrs['location'] = Point(longitude, latitude, srid=4326)
        if not attrs.get('location'):
            raise serializers.ValidationError({'location': 'Location or latitude/longitude is required.'})
        self.validate_location(attrs['location'])
        return attrs


class AlertLogSerializer(serializers.ModelSerializer):
    zone_name = serializers.SerializerMethodField()

    class Meta:
        model = AlertLog
        fields = [
            'id', 'zone_name', 'message', 'channel', 'recipient_count',
            'triggered_at', 'delivery_status', 'provider_message_id', 'delivered_at',
        ]

    def get_zone_name(self, obj):
        return obj.alert_zone.name if obj.alert_zone_id else None
