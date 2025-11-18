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

class SatelliteData(models.Model):
    """Satellite imagery and flood monitoring data"""
    SATELLITE_CHOICES = [
        ('sentinel1', 'Sentinel-1 (SAR Flood Detection)'),
        ('sentinel2', 'Sentinel-2 (Optical Validation)'),
        ('modis', 'MODIS (Global Monitoring)'),
        ('chirps', 'CHIRPS (Rainfall)'),
        ('gpm', 'NASA GPM (Precipitation)'),
    ]

    DATA_TYPE_CHOICES = [
        ('flood_extent', 'Flood Extent Mapping'),
        ('precipitation', 'Precipitation Data'),
        ('soil_moisture', 'Soil Moisture'),
        ('vegetation', 'Vegetation Index'),
        ('cloud_cover', 'Cloud Cover'),
    ]

    satellite = models.CharField(max_length=20, choices=SATELLITE_CHOICES)
    data_type = models.CharField(max_length=20, choices=DATA_TYPE_CHOICES)
    location = models.CharField(max_length=100, help_text="Area covered by the data")
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)

    # Data storage
    image_url = models.URLField(blank=True, help_text="URL to satellite image tile")
    geojson_data = models.JSONField(null=True, blank=True, help_text="GeoJSON flood polygons or features")
    metadata = models.JSONField(default=dict, help_text="Additional satellite metadata")

    # Temporal information
    capture_date = models.DateTimeField(help_text="When the satellite data was captured")
    processed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When this data expires")

    # Status and quality
    is_active = models.BooleanField(default=True)
    data_quality = models.CharField(max_length=20, default='good',
                                   choices=[('excellent', 'Excellent'),
                                           ('good', 'Good'),
                                           ('fair', 'Fair'),
                                           ('poor', 'Poor')])
    cloud_cover = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                     help_text="Cloud cover percentage")

    class Meta:
        ordering = ['-capture_date']
        indexes = [
            models.Index(fields=['satellite', 'data_type']),
            models.Index(fields=['location', 'capture_date']),
            models.Index(fields=['is_active', 'expires_at']),
        ]

    def __str__(self):
        return f"{self.satellite} - {self.data_type} - {self.location} ({self.capture_date.date()})"

    def is_expired(self):
        """Check if the satellite data has expired"""
        if self.expires_at:
            from django.utils import timezone
            return timezone.now() > self.expires_at
        return False

    def get_flood_risk_level(self):
        """Calculate flood risk level based on satellite data"""
        if self.data_type == 'flood_extent' and self.geojson_data:
            # Simple risk calculation based on flood area
            features = self.geojson_data.get('features', [])
            flood_area = len(features)  # Simplified - count of flood polygons
            if flood_area > 50:
                return 'critical'
            elif flood_area > 20:
                return 'high'
            elif flood_area > 5:
                return 'moderate'
            else:
                return 'low'
        elif self.data_type == 'precipitation':
            # Risk based on precipitation intensity
            precip = self.metadata.get('precipitation_mm', 0)
            if precip > 100:
                return 'critical'
            elif precip > 50:
                return 'high'
            elif precip > 20:
                return 'moderate'
            else:
                return 'low'
        return 'unknown'
