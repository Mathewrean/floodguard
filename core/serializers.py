from rest_framework import serializers
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.utils import timezone
from PIL import Image
import datetime
from .models import AlertZone, FloodReading, IncidentReport, AlertLog

class AlertZoneSerializer(serializers.ModelSerializer):
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
    class Meta:
        model = IncidentReport
        fields = '__all__'

class AlertLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertLog
        fields = '__all__'