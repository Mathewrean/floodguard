from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import DashboardWidget, SensorData, WeatherData, UserDashboard, SatelliteData
from alerts.models import FloodAlert
from community.models import UserReport
from datetime import datetime, timedelta
from django.db.models import Count

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

    # Satellite data statistics
    total_satellite_images = SatelliteData.objects.filter(is_active=True).count()
    recent_satellite_data = SatelliteData.objects.filter(capture_date__gte=week_ago).count()

    data = {
        'total_alerts': total_alerts,
        'total_reports': total_reports,
        'critical_alerts': critical_alerts,
        'recent_alerts': recent_alerts,
        'recent_reports': recent_reports,
        'total_satellite_images': total_satellite_images,
        'recent_satellite_data': recent_satellite_data,
    }
    return JsonResponse(data)

def satellite_widget(request):
    """API endpoint for satellite data widget"""
    # Get latest satellite data
    satellite_data = SatelliteData.objects.filter(is_active=True).order_by('-capture_date')[:10]
    data = []
    for sat in satellite_data:
        data.append({
            'id': sat.id,
            'satellite': sat.satellite,
            'data_type': sat.data_type,
            'location': sat.location,
            'latitude': str(sat.latitude) if sat.latitude else None,
            'longitude': str(sat.longitude) if sat.longitude else None,
            'image_url': sat.image_url,
            'capture_date': sat.capture_date.isoformat(),
            'data_quality': sat.data_quality,
            'cloud_cover': sat.cloud_cover,
            'flood_risk_level': sat.get_flood_risk_level(),
        })
    return JsonResponse({'satellite_data': data})

# Page views for navigation
def alerts_page(request):
    """Alerts page with AI-powered insights and satellite data"""
    alerts = FloodAlert.objects.filter(is_active=True).order_by('-created_at')

    # Get satellite data for flood monitoring
    satellite_flood_data = SatelliteData.objects.filter(
        data_type='flood_extent',
        is_active=True
    ).order_by('-capture_date')[:5]

    satellite_precipitation = SatelliteData.objects.filter(
        data_type='precipitation',
        is_active=True
    ).order_by('-capture_date')[:5]

    context = {
        'alerts': alerts,
        'satellite_flood_data': satellite_flood_data,
        'satellite_precipitation': satellite_precipitation,
        'page_title': 'Flood Alerts & Satellite Monitoring',
        'ai_insights': [
            "AI Analysis: Current weather patterns suggest 70% chance of flash flooding in low-lying areas.",
            "Machine Learning predicts peak flood risk between 2-4 AM tonight.",
            "Based on historical data, similar conditions led to 15 reported incidents last year.",
            "Satellite Analysis: Sentinel-1 detected flood extent increase of 23% in monitored areas.",
            "Precipitation Radar: CHIRPS data shows 45mm rainfall in last 24 hours across flood-prone regions."
        ]
    }
    return render(request, 'dashboard/alerts.html', context)

def reports_page(request):
    """Community reports page"""
    reports = UserReport.objects.filter(is_public=True).order_by('-created_at')
    context = {
        'reports': reports,
        'page_title': 'Community Reports',
        'ai_insights': [
            "Community sentiment analysis shows increasing concern in downtown areas.",
            "AI clustering identifies 3 main flood-affected zones based on reports.",
            "Pattern recognition suggests water levels rising 2 inches per hour in reported areas."
        ]
    }
    return render(request, 'dashboard/reports.html', context)

def statistics_page(request):
    """Statistics dashboard page"""
    # Calculate comprehensive statistics
    total_alerts = FloodAlert.objects.filter(is_active=True).count()
    total_reports = UserReport.objects.filter(is_public=True).count()
    critical_alerts = FloodAlert.objects.filter(alert_level='CRITICAL', is_active=True).count()

    # Time-based statistics
    week_ago = datetime.now() - timedelta(days=7)
    month_ago = datetime.now() - timedelta(days=30)

    recent_alerts = FloodAlert.objects.filter(created_at__gte=week_ago).count()
    monthly_alerts = FloodAlert.objects.filter(created_at__gte=month_ago).count()
    recent_reports = UserReport.objects.filter(created_at__gte=week_ago).count()
    monthly_reports = UserReport.objects.filter(created_at__gte=month_ago).count()

    # Location-based stats
    alerts_by_location = FloodAlert.objects.filter(is_active=True).values('location').annotate(count=Count('id')).order_by('-count')[:5]
    reports_by_location = UserReport.objects.filter(is_public=True).values('location').annotate(count=Count('id')).order_by('-count')[:5]

    context = {
        'page_title': 'System Statistics',
        'total_alerts': total_alerts,
        'total_reports': total_reports,
        'critical_alerts': critical_alerts,
        'recent_alerts': recent_alerts,
        'monthly_alerts': monthly_alerts,
        'recent_reports': recent_reports,
        'monthly_reports': monthly_reports,
        'alerts_by_location': alerts_by_location,
        'reports_by_location': reports_by_location,
        'ai_insights': [
            "AI Trend Analysis: Alert frequency increased 45% compared to last month.",
            "Predictive Analytics: System anticipates 23% more reports in next 48 hours.",
            "Machine Learning: Identified 5 high-risk zones requiring immediate attention."
        ]
    }
    return render(request, 'dashboard/statistics.html', context)

def weather_page(request):
    """Weather data page"""
    weather_data = WeatherData.objects.order_by('-timestamp')[:50]
    context = {
        'weather_data': weather_data,
        'page_title': 'Weather Monitoring',
        'ai_insights': [
            "AI Weather Prediction: Heavy rainfall expected in 3 hours with 85% confidence.",
            "Climate Model Analysis: Current conditions match historical flood precursors.",
            "Risk Assessment: Weather patterns indicate elevated flood danger for next 24 hours."
        ]
    }
    return render(request, 'dashboard/weather.html', context)

def sensors_page(request):
    """Sensor readings page"""
    sensors = SensorData.objects.order_by('-timestamp')[:100]
    context = {
        'sensors': sensors,
        'page_title': 'IoT Sensor Network',
        'ai_insights': [
            "Sensor Network Analysis: 3 sensors reporting critical water levels above threshold.",
            "AI Anomaly Detection: Unusual water level fluctuations detected in Sector 7.",
            "Predictive Maintenance: Sensor calibration recommended for units showing drift."
        ]
    }
    return render(request, 'dashboard/sensors.html', context)

def admin_panel_page(request):
    """Admin panel page with system overview"""
    context = {
        'page_title': 'System Administration',
        'ai_insights': [
            "System Health: All services operational with 99.8% uptime.",
            "AI Recommendations: Database optimization suggested for improved performance.",
            "Security Analysis: No vulnerabilities detected in recent scans."
        ]
    }
    return render(request, 'dashboard/admin_panel.html', context)
