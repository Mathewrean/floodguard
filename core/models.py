from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.gis.geos import Polygon
from django.conf import settings


class AlertZone(models.Model):
    name = models.CharField(max_length=100)
    polygon = models.PolygonField(srid=4326)
    risk_threshold = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Risk threshold (0.0-1.0) for triggering alerts"
    )
    risk_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Current calculated risk score (0.0-1.0)"
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
    def centroid(self):
        """Return the centroid of the zone polygon."""
        return self.polygon.centroid

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

    def clean(self):
        """Validate the alert zone"""
        super().clean()
        if self.polygon:
            # Check if polygon is valid
            if not self.polygon.valid:
                raise ValidationError({'polygon': 'Invalid polygon geometry'})
            
            # Check if polygon is within configured geographic bounds
            # Settings: GEO_BOUNDS = min_lon,min_lat,max_lon,max_lat
            bounds = getattr(settings, 'DEFAULT_GEO_BOUNDS', [33.0, -5.0, 42.0, 5.0])
            if len(bounds) == 4:
                allowed_bounds = Polygon.from_bbox(tuple(bounds))  # (min_lon, min_lat, max_lon, max_lat)
                if not self.polygon.within(allowed_bounds):
                    raise ValidationError({
                        'polygon': f'Polygon must be within allowed geographic bounds ({bounds})'
                    })

    def save(self, *args, **kwargs):
        """Override save to run validation and auto-deactivate expired overrides"""
        # Auto-deactivate manual override if expired
        if self.manual_override_active and self.manual_override_until:
            if timezone.now() > self.manual_override_until:
                self.manual_override_active = False
                self.manual_override_until = None
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Alert Zones"
        indexes = [
            models.Index(fields=['risk_score']),
            models.Index(fields=['manual_override_active']),
            models.Index(fields=['-updated_at']),
        ]


class FloodReading(models.Model):
    location = models.PointField(srid=4326)
    water_level_metres = models.FloatField(help_text="Water level in metres")
    risk_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Calculated risk score (0.0-1.0)",
        null=True,
        blank=True
    )
    source = models.CharField(max_length=100, help_text="Data source (e.g., sensor, satellite)")
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full multi-source feature vector from data ingestion"
    )
    verified = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reading at {self.location} - {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['-timestamp']),
            models.Index(fields=['risk_score']),
            models.Index(fields=['location']),  # GIST index will be created automatically for geometry field
        ]


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
        ('acknowledged', 'Acknowledged'),
    ]
    
    location = models.PointField(srid=4326)
    severity = models.IntegerField(
        choices=SEVERITY_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    description = models.TextField()
    photo = models.ImageField(upload_to='incident_photos/', blank=True, null=True)
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default='pending'
    )
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_reports', null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviewed_reports'
    )
    # Emergency acknowledgment fields
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_reports',
        help_text="Authority user who acknowledged this incident"
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the incident was acknowledged"
    )
    # Geographic clustering field
    cluster_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Identifier for geographic cluster of related reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Incident {self.id} - {self.get_severity_display()} - {self.status}"
    
    def save(self, *args, **kwargs):
        # Auto-assign cluster_id if not set and we have a location
        if not self.cluster_id and self.location:
            self.cluster_id = self.calculate_cluster_id()
        super().save(*args, **kwargs)
    
    def calculate_cluster_id(self, radius_meters=100):
        """
        Calculate a cluster ID based on geographic proximity.
        Reports within the specified radius (default 100m) will share the same cluster ID.
        """
        from django.contrib.gis.db.models import Union
        from django.contrib.gis.geos import Point
        from django.contrib.gis.measure import Distance
        
        # Find existing reports within radius
        nearby_reports = IncidentReport.objects.filter(
            location__distance_lte=(self.location, Distance(m=radius_meters))
        ).exclude(id=self.id if self.id else None)
        
        # If there are nearby reports, use the earliest one's cluster ID or create a new one
        if nearby_reports.exists():
            # Get the earliest report's cluster ID, or generate one if it doesn't have one
            earliest_report = nearby_reports.order_by('created_at').first()
            if earliest_report.cluster_id:
                return earliest_report.cluster_id
            else:
                # Generate a cluster ID based on the earliest report's location and time
                return f"cluster_{earliest_report.id}_{int(earliest_report.created_at.timestamp())}"
        else:
            # No nearby reports, create a new cluster ID based on this report's location and time
            return f"cluster_{int(timezone.now().timestamp())}_{hash((self.location.x, self.location.y)) % 10000}"
    
    @classmethod
    def cluster_recent_reports(cls, hours=24, radius_meters=100):
        """
        Cluster recent reports geographically.
        This can be run as a periodic task to update cluster assignments.
        """
        from django.contrib.gis.measure import Distance
        from django.utils import timezone
        import datetime
        
        cutoff_time = timezone.now() - datetime.timedelta(hours=hours)
        recent_reports = cls.objects.filter(
            created_at__gte=cutoff_time
        ).filter(
            cluster_id__isnull=True
        ) | cls.objects.filter(
            created_at__gte=cutoff_time,
            cluster_id=''
        )
        
        for report in recent_reports:
            if not report.cluster_id:
                report.cluster_id = report.calculate_cluster_id(radius_meters)
                report.save(update_fields=['cluster_id'])
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['severity']),
            models.Index(fields=['cluster_id']),
            models.Index(fields=['location']),
            models.Index(fields=['submitted_by', '-created_at']),
        ]


class AlertLog(models.Model):
    alert_zone = models.ForeignKey(AlertZone, on_delete=models.CASCADE, related_name='alert_logs')
    message = models.TextField()
    channel = models.CharField(max_length=50, help_text="e.g., SMS, Email, App Push")
    recipient_count = models.IntegerField(default=0)
    triggered_at = models.DateTimeField(auto_now_add=True)
    # SMS delivery tracking fields
    delivery_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('sent', 'Sent'),
            ('delivered', 'Delivered'),
            ('failed', 'Failed'),
            ('undelivered', 'Undelivered'),
        ],
        default='pending',
        help_text="Delivery status of the alert"
    )
    provider_message_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Message ID from the SMS provider (e.g., Africa's Talking)"
    )
    delivered_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when the message was delivered"
    )

    def __str__(self):
        return f"Alert for {self.alert_zone.name} at {self.triggered_at}"

    class Meta:
        ordering = ['-triggered_at']
        verbose_name_plural = "Alert Logs"
        indexes = [
            models.Index(fields=['-triggered_at']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['alert_zone', '-triggered_at']),
        ]


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
    phone_number = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        help_text="Phone number for SMS alerts (international format: +[country code][number])"
    )
    phone_verified = models.BooleanField(
        default=False,
        help_text="Whether the phone number has been verified via OTP"
    )
    sms_enabled = models.BooleanField(
        default=True,
        help_text="User consent to receive SMS alerts"
    )

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
