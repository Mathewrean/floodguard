from django.db import models
from django.contrib.auth.models import User

class UserReport(models.Model):
    REPORT_TYPES = [
        ('FLOODING', 'Flooding Observed'),
        ('DAMAGE', 'Property Damage'),
        ('ROAD_CLOSURE', 'Road Closure'),
        ('POWER_OUTAGE', 'Power Outage'),
        ('EMERGENCY', 'Emergency Situation'),
        ('OTHER', 'Other'),
    ]

    VERIFICATION_STATUS = [
        ('PENDING', 'Pending Verification'),
        ('VERIFIED', 'Verified'),
        ('FALSE_POSITIVE', 'False Positive'),
        ('DUPLICATE', 'Duplicate'),
    ]

    reporter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES, default='FLOODING')
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=[
        ('LOW', 'Low'),
        ('MODERATE', 'Moderate'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ], default='MODERATE')
    verification_status = models.CharField(max_length=15, choices=VERIFICATION_STATUS, default='PENDING')
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_reports')
    verified_at = models.DateTimeField(null=True, blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.report_type}: {self.title}"

    class Meta:
        ordering = ['-created_at']

class ReportMedia(models.Model):
    report = models.ForeignKey(UserReport, on_delete=models.CASCADE, related_name='media')
    media_type = models.CharField(max_length=10, choices=[
        ('IMAGE', 'Image'),
        ('VIDEO', 'Video'),
        ('AUDIO', 'Audio'),
    ], default='IMAGE')
    file = models.FileField(upload_to='reports/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.media_type} for {self.report.title}"

class ReportComment(models.Model):
    report = models.ForeignKey(UserReport, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    is_official = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Comment by {self.author.username} on {self.report.title}"

    class Meta:
        ordering = ['created_at']
