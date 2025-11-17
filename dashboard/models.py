from django.db import models
from django.contrib.auth.models import User

class DashboardWidget(models.Model):
    WIDGET_TYPES = [
        ('ALERTS', 'Active Alerts'),
        ('REPORTS', 'Community Reports'),
        ('WEATHER', 'Weather Data'),
        ('SENSORS', 'Sensor Readings'),
        ('MAP', 'Interactive Map'),
        ('CHART', 'Data Chart'),
        ('STATS', 'Statistics'),
    ]

    title = models.CharField(max_length=100)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES, default='STATS')
    position_x = models.IntegerField(default=0)
    position_y = models.IntegerField(default=0)
    width = models.IntegerField(default=4)
    height = models.IntegerField(default=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.widget_type}: {self.title}"

class UserDashboard(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    widgets = models.ManyToManyField(DashboardWidget, through='UserWidgetConfig')
    layout = models.JSONField(default=dict)  # Store dashboard layout configuration
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Dashboard for {self.user.username}"

class UserWidgetConfig(models.Model):
    user_dashboard = models.ForeignKey(UserDashboard, on_delete=models.CASCADE)
    widget = models.ForeignKey(DashboardWidget, on_delete=models.CASCADE)
    is_visible = models.BooleanField(default=True)
    custom_config = models.JSONField(default=dict)  # Store widget-specific configuration
    position = models.IntegerField(default=0)

    class Meta:
        unique_together = ['user_dashboard', 'widget']
        ordering = ['position']

class SensorData(models.Model):
    sensor_id = models.CharField(max_length=50)
    sensor_type = models.CharField(max_length=20, choices=[
        ('RAIN_GAUGE', 'Rain Gauge'),
        ('WATER_LEVEL', 'Water Level'),
        ('WEATHER_STATION', 'Weather Station'),
        ('CAMERA', 'Camera'),
    ], default='RAIN_GAUGE')
    location = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    value = models.FloatField()
    unit = models.CharField(max_length=20, default='mm')  # mm for rain, m for water level, etc.
    timestamp = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sensor_type} at {self.location}: {self.value} {self.unit}"

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['sensor_id', 'timestamp']),
            models.Index(fields=['sensor_type', 'timestamp']),
        ]

class WeatherData(models.Model):
    location = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    temperature = models.FloatField(null=True, blank=True)  # Celsius
    humidity = models.FloatField(null=True, blank=True)  # Percentage
    precipitation = models.FloatField(default=0)  # mm
    wind_speed = models.FloatField(null=True, blank=True)  # m/s
    wind_direction = models.FloatField(null=True, blank=True)  # Degrees
    pressure = models.FloatField(null=True, blank=True)  # hPa
    visibility = models.FloatField(null=True, blank=True)  # km
    timestamp = models.DateTimeField()
    source = models.CharField(max_length=50, default='NOAA')  # Data source
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Weather at {self.location}: {self.temperature}°C, {self.precipitation}mm"

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['location', 'timestamp']),
        ]
