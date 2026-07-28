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
        if self.manual_override_until:
            return timezone.now() < self.manual_override_until
        return True

    def clean(self):
        """Validate the alert zone"""
        super().clean()
        if self.polygon:
            if not self.polygon.valid:
                raise ValidationError({'polygon': 'Invalid polygon geometry'})
            
            bounds = getattr(settings, 'DEFAULT_GEO_BOUNDS', None)
            if bounds and len(bounds) == 4:
                allowed_bounds = Polygon.from_bbox(tuple(bounds))
                if not self.polygon.within(allowed_bounds):
                    raise ValidationError({
                        'polygon': f'Polygon must be within allowed geographic bounds ({bounds})'
                    })

    def save(self, *args, **kwargs):
        """Override save to auto-deactivate expired overrides"""
        if self.manual_override_active and self.manual_override_until:
            if timezone.now() > self.manual_override_until:
                self.manual_override_active = False
                self.manual_override_until = None
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
        ('super_admin', 'Super Admin'),
        ('govt_national', 'Government Official (National)'),
        ('govt_county', 'Government Official (County)'),
        ('emergency_responder', 'Emergency Responder'),
        ('meteo_officer', 'Meteorological Officer'),
        ('ngo_humanitarian', 'NGO/Humanitarian Worker'),
        ('citizen', 'Citizen/Public User'),
        ('researcher', 'Researcher/Analyst'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(
        max_length=30,
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


class FloodPrediction(models.Model):
    zone = models.ForeignKey(AlertZone, on_delete=models.CASCADE, related_name='predictions')
    predicted_at = models.DateTimeField(auto_now_add=True)
    target_date = models.DateField(help_text="Date for which this prediction is made")
    risk_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Predicted risk score (0.0-1.0)"
    )
    water_level_metres = models.FloatField(
        null=True,
        blank=True,
        help_text="Predicted water level in metres"
    )
    river_discharge_m3s = models.FloatField(
        null=True,
        blank=True,
        help_text="Predicted river discharge in m3/s"
    )
    confidence = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Prediction confidence (0.0-1.0)"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Source data used for prediction"
    )

    class Meta:
        ordering = ['target_date']
        indexes = [
            models.Index(fields=['zone', 'target_date']),
            models.Index(fields=['-predicted_at']),
        ]
        unique_together = ['zone', 'target_date']

    def __str__(self):
        return f"Prediction for {self.zone.name} on {self.target_date}"


class AlertZoneActivity(models.Model):
    """
    Tracks user interactions with zones for dynamic zone management.
    This model enables the system to:
    - Record when users check in to zones via GPS
    - Determine which zones are actively used
    - Support dynamic zone creation based on user density
    """
    SOURCE_CHOICES = [
        ('static', 'Static / Predefined'),
        ('dynamic', 'Dynamic / GPS-derived'),
        ('user', 'User-created'),
        ('imported', 'Imported'),
    ]

    zone = models.ForeignKey(AlertZone, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='zone_activities', null=True, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='dynamic')
    latitude = models.FloatField(help_text="User's latitude at check-in")
    longitude = models.FloatField(help_text="User's longitude at check-in")
    accuracy_meters = models.FloatField(null=True, blank=True, help_text="GPS accuracy in meters")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['zone', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['source']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Activity: {self.zone.name} at {self.created_at}"


class Milestone(models.Model):
    """Project milestones for impact tracking and transparency."""
    CATEGORIES = [
        ('technical', 'Technical'),
        ('community', 'Community'),
        ('business', 'Business'),
        ('partnership', 'Partnership'),
    ]
    title = models.CharField(max_length=200)
    description = models.TextField()
    achieved_date = models.DateField()
    category = models.CharField(max_length=20, choices=CATEGORIES)
    evidence_url = models.URLField(blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-achieved_date']
        indexes = [
            models.Index(fields=['category']),
            models.Index(fields=['is_public']),
            models.Index(fields=['-achieved_date']),
        ]

    def __str__(self):
        return f"{self.title} ({self.achieved_date})"


class BeneficiaryGroup(models.Model):
    """Groups trained/enrolled in flood preparedness programs."""
    TYPES = [
        ('community', 'Community Group'),
        ('school', 'School'),
        ('ngo', 'NGO'),
        ('government', 'Government'),
        ('business', 'Business'),
    ]
    name = models.CharField(max_length=200)
    group_type = models.CharField(max_length=20, choices=TYPES)
    member_count = models.IntegerField()
    location = models.CharField(max_length=200)
    enrolled_date = models.DateField()
    trained = models.BooleanField(default=False)
    training_date = models.DateField(null=True, blank=True)
    contact = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-enrolled_date']
        indexes = [
            models.Index(fields=['group_type']),
            models.Index(fields=['trained']),
            models.Index(fields=['-enrolled_date']),
        ]

    def __str__(self):
        return f"{self.name} ({self.member_count} members)"


class MonthlyReport(models.Model):
    """Monthly operational reports for impact tracking."""
    period_start = models.DateField()
    period_end = models.DateField()
    alerts_sent = models.IntegerField(default=0)
    reports_received = models.IntegerField(default=0)
    reports_verified = models.IntegerField(default=0)
    high_risk_events = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    zones_monitored = models.IntegerField(default=0)
    uptime_pct = models.FloatField(default=100.0)
    generated_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_start']
        indexes = [
            models.Index(fields=['-period_start']),
            models.Index(fields=['-generated_at']),
        ]

    def __str__(self):
        return f"Monthly Report: {self.period_start} to {self.period_end}"


# ============================================================
# Layer 1 - Administrative Boundaries
# ============================================================

class AdministrativeBoundary(models.Model):
    BOUNDARY_TYPES = [
        ('country', 'Country'),
        ('county', 'County'),
        ('constituency', 'Constituency'),
        ('ward', 'Ward'),
        ('village', 'Village'),
        ('river', 'River'),
        ('protected_area', 'Protected Area'),
    ]

    name = models.CharField(max_length=200)
    boundary_type = models.CharField(max_length=30, choices=BOUNDARY_TYPES)
    geometry = models.GeometryField(srid=4326)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    metadata = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=100, default='natural_earth')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['boundary_type']),
            models.Index(fields=['parent']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_boundary_type_display()})"


# ============================================================
# Layer 2 - H3 Spatial Grid Intelligence
# ============================================================

class H3Cell(models.Model):
    h3_index = models.CharField(max_length=50, unique=True, db_index=True)
    resolution = models.IntegerField()
    centroid_lat = models.FloatField()
    centroid_lon = models.FloatField()
    population_density = models.FloatField(null=True, blank=True)
    road_density = models.FloatField(null=True, blank=True)
    building_density = models.FloatField(null=True, blank=True)
    terrain_complexity = models.FloatField(null=True, blank=True)
    historical_flood_frequency = models.FloatField(default=0.0)
    current_risk_score = models.FloatField(default=0.0)
    confidence = models.FloatField(default=0.0)
    last_updated = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['resolution']),
            models.Index(fields=['-current_risk_score']),
            models.Index(fields=['-last_updated']),
        ]

    def __str__(self):
        return f"H3 {self.h3_index} (res {self.resolution})"


class H3CellRelationship(models.Model):
    RELATIONSHIP_TYPES = [
        ('parent', 'Parent'),
        ('child', 'Child'),
        ('neighbor', 'Neighbor'),
        ('k_ring', 'K-Ring'),
    ]

    source_cell = models.ForeignKey(H3Cell, on_delete=models.CASCADE, related_name='outgoing_relationships')
    target_cell = models.ForeignKey(H3Cell, on_delete=models.CASCADE, related_name='incoming_relationships')
    relationship_type = models.CharField(max_length=20, choices=RELATIONSHIP_TYPES)
    distance_km = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['source_cell', 'target_cell', 'relationship_type']
        indexes = [
            models.Index(fields=['source_cell', 'relationship_type']),
            models.Index(fields=['target_cell', 'relationship_type']),
        ]

    def __str__(self):
        return f"{self.source_cell.h3_index} -> {self.target_cell.h3_index} ({self.relationship_type})"


# ============================================================
# Layer 3 - Dynamic Flood Zones
# ============================================================

class DynamicZone(models.Model):
    ZONE_STATES = [
        ('new', 'New'),
        ('monitoring', 'Monitoring'),
        ('active', 'Active'),
        ('escalated', 'Escalated'),
        ('stabilizing', 'Stabilizing'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    ]

    CREATION_SOURCES = [
        ('weather', 'Weather Update'),
        ('community', 'Community Report'),
        ('river_discharge', 'River Discharge'),
        ('rainfall', 'Extreme Rainfall'),
        ('satellite', 'Satellite/Open Data'),
        ('authority', 'Authority Input'),
        ('merged', 'Merged from multiple zones'),
        ('split', 'Split from parent zone'),
    ]

    name = models.CharField(max_length=200)
    state = models.CharField(max_length=20, choices=ZONE_STATES, default='new')
    creation_source = models.CharField(max_length=30, choices=CREATION_SOURCES)
    h3_cells = models.ManyToManyField(H3Cell, related_name='dynamic_zones')
    geometry = models.GeometryField(srid=4326)
    risk_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    confidence = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    cause = models.TextField(blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    population_exposed = models.IntegerField(null=True, blank=True)
    buildings_affected = models.IntegerField(null=True, blank=True)
    roads_affected = models.JSONField(default=list, blank=True)
    critical_infrastructure = models.JSONField(default=list, blank=True)
    recommended_actions = models.JSONField(default=list, blank=True)
    priority = models.IntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(10)])
    resource_requirements = models.JSONField(default=dict, blank=True)
    evacuation_advice = models.TextField(blank=True)
    emergency_response_level = models.CharField(max_length=50, blank=True)
    parent_zone = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_zones')
    merged_from = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='merged_into')
    authority_override = models.BooleanField(default=False)
    override_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['state']),
            models.Index(fields=['creation_source']),
            models.Index(fields=['-risk_score']),
            models.Index(fields=['-updated_at']),
            models.Index(fields=['priority']),
        ]
        ordering = ['-risk_score', '-updated_at']

    def __str__(self):
        return f"{self.name} ({self.get_state_display()}) - {self.risk_score:.2f}"


class FloodPropagation(models.Model):
    zone = models.ForeignKey(DynamicZone, on_delete=models.CASCADE, related_name='propagations')
    predicted_cells = models.ManyToManyField(H3Cell, related_name='propagation_predictions')
    forecast_hours = models.IntegerField()
    predicted_risk_score = models.FloatField(default=0.0)
    confidence = models.FloatField(default=0.0)
    spread_direction = models.CharField(max_length=100, blank=True)
    estimated_arrival = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['zone', 'forecast_hours']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"Propagation for {self.zone.name} +{self.forecast_hours}h"


class ZoneLifecycleLog(models.Model):
    zone = models.ForeignKey(DynamicZone, on_delete=models.CASCADE, related_name='lifecycle_logs')
    from_state = models.CharField(max_length=20, choices=DynamicZone.ZONE_STATES)
    to_state = models.CharField(max_length=20, choices=DynamicZone.ZONE_STATES)
    reason = models.TextField(blank=True)
    triggered_by = models.CharField(max_length=100, default='system')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['zone', '-created_at']),
        ]

    def __str__(self):
        return f"{self.zone.name}: {self.from_state} -> {self.to_state}"


# ============================================================
# Extended AlertZone for backward compatibility
# ============================================================

AlertZone.add_to_class('is_active', models.BooleanField(default=True, help_text="Whether the zone is currently active"))
AlertZone.add_to_class('creation_source', models.CharField(max_length=30, choices=DynamicZone.CREATION_SOURCES, default='authority', help_text="Source of zone creation"))
AlertZone.add_to_class('confidence', models.FloatField(default=0.0, help_text="Confidence in zone accuracy (0.0-1.0)"))
AlertZone.add_to_class('expires_at', models.DateTimeField(null=True, blank=True, help_text="When the zone expires (null for permanent)"))
AlertZone.add_to_class('metadata', models.JSONField(default=dict, blank=True, help_text="Additional zone metadata"))
