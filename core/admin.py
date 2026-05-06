from django.contrib import admin

from django.contrib import admin
from django.contrib.gis.admin import OSMGeoAdmin
from .models import AlertZone, FloodReading, IncidentReport, AlertLog


@admin.register(AlertZone)
class AlertZoneAdmin(OSMGeoAdmin):
    list_display = ('name', 'risk_threshold', 'created_at')
    search_fields = ('name',)


@admin.register(FloodReading)
class FloodReadingAdmin(OSMGeoAdmin):
    list_display = ('location', 'water_level_metres', 'risk_score', 'source', 'verified', 'timestamp')
    list_filter = ('verified', 'source', 'timestamp')
    search_fields = ('source',)


@admin.register(IncidentReport)
class IncidentReportAdmin(OSMGeoAdmin):
    list_display = ('location', 'severity', 'status', 'submitted_by', 'reviewed_by', 'created_at')
    list_filter = ('severity', 'status', 'created_at')
    search_fields = ('description',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = ('alert_zone', 'channel', 'recipient_count', 'triggered_at')
    list_filter = ('channel', 'triggered_at')
    search_fields = ('message',)
