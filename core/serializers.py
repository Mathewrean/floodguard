from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import AlertZone, FloodReading, IncidentReport, AlertLog

class AlertZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertZone
        fields = '__all__'

class FloodReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = FloodReading
        fields = '__all__'

class IncidentReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentReport
        fields = '__all__'

class AlertLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertLog
        fields = '__all__'