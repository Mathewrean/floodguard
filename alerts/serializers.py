from rest_framework import serializers
from .models import FloodAlert

class FloodAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = FloodAlert
        fields = ['id', 'location', 'parameter', 'threshold', 'triggered_at', 'severity']
