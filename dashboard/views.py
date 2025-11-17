from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import DashboardWidget, SensorData, WeatherData, UserDashboard
from alerts.models import FloodAlert
from community.models import UserReport
from datetime import datetime, timedelta

def dashboard_home(request):
    """Main dashboard view"""
    return render(request, 'dashboard/home.html')

@login_required
def user_dashboard(request):
    """Personalized dashboard for logged-in users"""
    try:
        user_dash = UserDashboard.objects.get(user=request.user)
        widgets = user_dash.widgets.filter(is_active=True)
    except UserDashboard.DoesNotExist:
        # Create default dashboard if none exists
        widgets = DashboardWidget.objects.filter(is_active=True)[:6]  # Default widgets

    context = {
        'widgets': widgets,
    }
    return render(request, 'dashboard/user_dashboard.html', context)

def alerts_widget(request):
    """API endpoint for alerts widget data"""
    alerts = FloodAlert.objects.filter(is_active=True).order_by('-created_at')[:5]
    data = []
    for alert in alerts:
        data.append({
            'id': alert.id,
            'title': alert.title,
            'level': alert.alert_level,
            'location': alert.location,
            'created_at': alert.created_at.isoformat(),
        })
    return JsonResponse({'alerts': data})

def reports_widget(request):
    """API endpoint for community reports widget data"""
    reports = UserReport.objects.filter(is_public=True).order_by('-created_at')[:5]
    data = []
    for report in reports:
        data.append({
            'id': report.id,
            'title': report.title,
            'type': report.report_type,
            'location': report.location,
            'severity': report.severity,
            'created_at': report.created_at.isoformat(),
        })
    return JsonResponse({'reports': data})

def weather_widget(request):
    """API endpoint for weather widget data"""
    # Get latest weather data for different locations
    weather_data = WeatherData.objects.order_by('-timestamp')[:10]
    data = []
    for weather in weather_data:
        data.append({
            'location': weather.location,
            'temperature': weather.temperature,
            'humidity': weather.humidity,
            'precipitation': weather.precipitation,
            'wind_speed': weather.wind_speed,
            'timestamp': weather.timestamp.isoformat(),
        })
    return JsonResponse({'weather': data})

def sensors_widget(request):
    """API endpoint for sensors widget data"""
    # Get latest sensor readings
    sensors = SensorData.objects.order_by('-timestamp')[:20]
    data = []
    for sensor in sensors:
        data.append({
            'sensor_id': sensor.sensor_id,
            'type': sensor.sensor_type,
            'location': sensor.location,
            'value': sensor.value,
            'unit': sensor.unit,
            'timestamp': sensor.timestamp.isoformat(),
        })
    return JsonResponse({'sensors': data})

def stats_widget(request):
    """API endpoint for statistics widget data"""
    # Calculate some basic statistics
    total_alerts = FloodAlert.objects.filter(is_active=True).count()
    total_reports = UserReport.objects.filter(is_public=True).count()
    critical_alerts = FloodAlert.objects.filter(alert_level='CRITICAL', is_active=True).count()

    # Recent activity (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    recent_alerts = FloodAlert.objects.filter(created_at__gte=week_ago).count()
    recent_reports = UserReport.objects.filter(created_at__gte=week_ago).count()

    data = {
        'total_alerts': total_alerts,
        'total_reports': total_reports,
        'critical_alerts': critical_alerts,
        'recent_alerts': recent_alerts,
        'recent_reports': recent_reports,
    }
    return JsonResponse(data)
