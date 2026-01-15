from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import FloodAlert, AlertRecipient
import json
from datetime import datetime

def alert_list(request):
    """API endpoint to list active flood alerts"""
    alerts = FloodAlert.objects.filter(is_active=True).order_by('-created_at')
    alert_data = []
    for alert in alerts:
        alert_data.append({
            'id': alert.id,
            'title': alert.title,
            'description': alert.description,
            'alert_level': alert.alert_level,
            'location': alert.location,
            'latitude': str(alert.latitude) if alert.latitude else None,
            'longitude': str(alert.longitude) if alert.longitude else None,
            'start_time': alert.start_time.isoformat(),
            'end_time': alert.end_time.isoformat() if alert.end_time else None,
            'created_at': alert.created_at.isoformat(),
        })
    return JsonResponse({'alerts': alert_data})

@login_required
@csrf_exempt
def create_alert(request):
    """API endpoint to create a new flood alert"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        alert = FloodAlert.objects.create(
            title=data['title'],
            description=data['description'],
            alert_level=data.get('alert_level', 'MODERATE'),
            location=data['location'],
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            affected_area=data.get('affected_area', ''),
            start_time=datetime.fromisoformat(data['start_time']),
            end_time=datetime.fromisoformat(data['end_time']) if data.get('end_time') else None,
            created_by=request.user,
        )
        return JsonResponse({
            'id': alert.id,
            'message': 'Alert created successfully'
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def alert_detail(request, alert_id):
    """API endpoint to get alert details"""
    alert = get_object_or_404(FloodAlert, id=alert_id)
    alert_data = {
        'id': alert.id,
        'title': alert.title,
        'description': alert.description,
        'alert_level': alert.alert_level,
        'location': alert.location,
        'latitude': str(alert.latitude) if alert.latitude else None,
        'longitude': str(alert.longitude) if alert.longitude else None,
        'affected_area': alert.affected_area,
        'start_time': alert.start_time.isoformat(),
        'end_time': alert.end_time.isoformat() if alert.end_time else None,
        'is_active': alert.is_active,
        'created_at': alert.created_at.isoformat(),
        'updated_at': alert.updated_at.isoformat(),
    }
    return JsonResponse(alert_data)
