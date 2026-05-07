from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class AlertZone(models.Model):
    name = models.CharField(max_length=100)
    polygon = models.PolygonField(srid=4326)
    risk_threshold = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Risk threshold (0.0-1.0) for triggering alerts"
    )
    # Manual alert override fields
    manual_override_active = models.BooleanField(
        default=False,
        help_text="When active, suppresses automatic alert triggering for this zone"
    )
    manual_override_until = models.DateTimeField(
        null=True, blank=True,
        help_text="Override is active until this time (if set)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def is_override_active(self):
        """Check if manual override is currently active"""
        if not self.manual_override_active:
            return False
        if self.manual_override_until and timezone.now() > self.manual_override_until:
            # Override has expired, deactivate it
            self.manual_override_active = False
            self.manual_override_until = None
            self.save(update_fields=['manual_override_active', 'manual_override_until'])
            return False
        return True

    class Meta:
        verbose_name_plural = "Alert Zones"


class FloodReading(models.Model):
    location = models.PointField(srid=4326)
    water_level_metres = models.FloatField(help_text="Water level in metres")
    risk_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Calculated risk score (0.0-1.0)"
    )
    source = models.CharField(max_length=100, help_text="Data source (e.g., sensor, satellite)")
    verified = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reading at {self.location} - {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']


class IncidentReport(models.Model):
    SEVERITY_CHOICES = [
        (1, 'Low'),
        (2, 'Medium-Low'),
        (3, 'Medium'),
        (4, 'High'),
        (5, 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    location = models.PointField(srid=4326)
    severity = models.IntegerField(
        choices=SEVERITY_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    description = models.TextField()
    photo = models.ImageField(upload_to='incident_photos/', blank=True, null=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_reports')
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviewed_reports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Incident {self.id} - {self.get_severity_display()} - {self.status}"

    class Meta:
        ordering = ['-created_at']


class AlertLog(models.Model):
    alert_zone = models.ForeignKey(AlertZone, on_delete=models.CASCADE, related_name='alert_logs')
    message = models.TextField()
    channel = models.CharField(max_length=50, help_text="e.g., SMS, Email, App Push")
    recipient_count = models.IntegerField(default=0)
    triggered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Alert for {self.alert_zone.name} at {self.triggered_at}"

    class Meta:
        ordering = ['-triggered_at']
        verbose_name_plural = "Alert Logs"


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('citizen', 'Citizen'),
        ('authority', 'Authority'),
        ('admin', 'Admin'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='citizen',
        help_text="User role in the system"
    )
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"