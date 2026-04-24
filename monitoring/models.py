from django.db import models

class RiverReading(models.Model):
    source = models.CharField(max_length=100)
    location = models.CharField(max_length=150)
    latitude = models.FloatField()
    longitude = models.FloatField()
    water_level = models.FloatField(null=True, blank=True)  # meters
    discharge = models.FloatField(null=True, blank=True)    # m³/s
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
