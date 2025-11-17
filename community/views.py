from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import UserReport, ReportComment
import json
from datetime import datetime

def report_list(request):
    """API endpoint to list community reports"""
    reports = UserReport.objects.filter(is_public=True).order_by('-created_at')
    report_data = []
    for report in reports:
        report_data.append({
            'id': report.id,
            'title': report.title,
            'description': report.description,
            'report_type': report.report_type,
            'location': report.location,
            'latitude': str(report.latitude) if report.latitude else None,
            'longitude': str(report.longitude) if report.longitude else None,
            'severity': report.severity,
            'verification_status': report.verification_status,
            'created_at': report.created_at.isoformat(),
            'reporter': report.reporter.username if report.reporter else 'Anonymous',
        })
    return JsonResponse({'reports': report_data})

@login_required
@csrf_exempt
def create_report(request):
    """API endpoint to create a community report"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        report = UserReport.objects.create(
            reporter=request.user,
            report_type=data['report_type'],
            title=data['title'],
            description=data['description'],
            location=data['location'],
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            address=data.get('address', ''),
            severity=data.get('severity', 'MODERATE'),
        )
        return JsonResponse({
            'id': report.id,
            'message': 'Report submitted successfully'
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def report_detail(request, report_id):
    """API endpoint to get report details"""
    report = get_object_or_404(UserReport, id=report_id, is_public=True)
    report_data = {
        'id': report.id,
        'title': report.title,
        'description': report.description,
        'report_type': report.report_type,
        'location': report.location,
        'latitude': str(report.latitude) if report.latitude else None,
        'longitude': str(report.longitude) if report.longitude else None,
        'address': report.address,
        'severity': report.severity,
        'verification_status': report.verification_status,
        'is_public': report.is_public,
        'created_at': report.created_at.isoformat(),
        'updated_at': report.updated_at.isoformat(),
        'reporter': report.reporter.username if report.reporter else 'Anonymous',
        'comments_count': report.comments.count(),
    }
    return JsonResponse(report_data)

@login_required
@csrf_exempt
def add_comment(request, report_id):
    """API endpoint to add a comment to a report"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    report = get_object_or_404(UserReport, id=report_id)
    try:
        data = json.loads(request.body)
        comment = ReportComment.objects.create(
            report=report,
            author=request.user,
            content=data['content'],
            is_official=data.get('is_official', False),
        )
        return JsonResponse({
            'id': comment.id,
            'message': 'Comment added successfully'
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
