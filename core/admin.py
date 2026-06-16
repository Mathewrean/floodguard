from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile


@admin.register(AlertZone)
class AlertZoneAdmin(GISModelAdmin):
    list_display = ('name', 'risk_threshold', 'created_at')
    search_fields = ('name',)


@admin.register(FloodReading)
class FloodReadingAdmin(GISModelAdmin):
    list_display = ('location', 'water_level_metres', 'risk_score', 'source', 'verified', 'timestamp')
    list_filter = ('verified', 'source', 'timestamp')
    search_fields = ('source',)


@admin.register(IncidentReport)
class IncidentReportAdmin(GISModelAdmin):
    list_display = ('location', 'severity', 'status', 'submitted_by', 'reviewed_by', 'created_at')
    list_filter = ('severity', 'status', 'created_at')
    search_fields = ('description',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = ('alert_zone', 'channel', 'recipient_count', 'triggered_at')
    list_filter = ('channel', 'triggered_at')
    search_fields = ('message',)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'profile'


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role')
    
    def get_role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, 'profile') else '-'
    get_role.short_description = 'Role'


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
