from django.db import models

class FloodAlert(models.Model):
    location = models.CharField(max_length=100)
    parameter = models.CharField(max_length=50, default="river_level")
    value = models.FloatField()
    threshold = models.FloatField(default=0.0)
    severity = models.CharField(max_length=20, default="LOW")
    triggered_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"{self.location} - {self.severity}"
