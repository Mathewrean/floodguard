from django.db import models
from django.contrib.auth.models import User

class FloodAlert(models.Model):
    ALERT_LEVELS = [
        ('LOW', 'Low Risk'),
        ('MODERATE', 'Moderate Risk'),
        ('HIGH', 'High Risk'),
        ('CRITICAL', 'Critical Risk'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    alert_level = models.CharField(max_length=10, choices=ALERT_LEVELS, default='LOW')
    location = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    affected_area = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.alert_level}: {self.title}"

    class Meta:
        ordering = ['-created_at']

class AlertRecipient(models.Model):
    alert = models.ForeignKey(FloodAlert, on_delete=models.CASCADE, related_name='recipients')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    notified_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    notification_method = models.CharField(max_length=20, choices=[
        ('EMAIL', 'Email'),
        ('SMS', 'SMS'),
        ('PUSH', 'Push Notification'),
        ('VOICE', 'Voice Call'),
    ], default='EMAIL')

    def __str__(self):
        return f"{self.user.username} - {self.alert.title}"

    class Meta:
        unique_together = ['alert', 'user']
