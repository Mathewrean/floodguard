from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.db import IntegrityError, transaction
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
from .models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile
from django.contrib.gis.geos import Point
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

# REST API imports
from rest_framework import viewsets, permissions, status, serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework_gis.serializers import GeometryField

# Serializers for API (imported from serializers.py)
from .serializers import (
    AlertZoneSerializer,
    FloodReadingSerializer,
    IncidentReportSerializer,
    AlertLogSerializer
)

# ViewSets
from rest_framework.pagination import LimitOffsetPagination

# ... other imports ...

class AlertZoneViewSet(viewsets.ModelViewSet):
    queryset = AlertZone.objects.all().prefetch_related('alert_logs').order_by('-risk_score', 'name')
    serializer_class = AlertZoneSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = LimitOffsetPagination
    pagination_class.default_limit = 10
    pagination_class.max_limit = 500

    def get_queryset(self):
        """Support filtering by bounding box for map viewport loading."""
        queryset = AlertZone.objects.all().prefetch_related('alert_logs').order_by('-risk_score', 'name')

        # Bounding box filter: ?bbox=min_lon,min_lat,max_lon,max_lat
        bbox_param = self.request.query_params.get('bbox')
        if bbox_param:
            try:
                coords = [float(c) for c in bbox_param.split(',')]
                if len(coords) == 4:
                    min_lon, min_lat, max_lon, max_lat = coords
                    bbox_polygon = Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat))
                    queryset = queryset.filter(polygon__intersects=bbox_polygon)
            except (ValueError, TypeError):
                pass

        # For list action, pagination will handle limit automatically
        # For other actions (like manual_override), we must not slice
        return queryset

    @action(detail=True, methods=['post'])
    def manual_override(self, request, pk=None):
        zone = self.get_object()
        # Only authority or admin can set manual override
        if not (request.user.groups.filter(name='EmergencyTeam').exists() or request.user.is_superuser):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        
        active = request.data.get('active')
        if active is None:
            return Response({'error': 'active field is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        zone.manual_override_active = bool(active)
        duration_hours = request.data.get('duration_hours')
        if active and duration_hours:
            try:
                hours = int(duration_hours)
                zone.manual_override_until = timezone.now() + timedelta(hours=hours)
            except (ValueError, TypeError):
                return Response({'error': 'duration_hours must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            zone.manual_override_until = None
        
        zone.save()
        return Response({
            'status': 'updated',
            'manual_override_active': zone.manual_override_active,
            'manual_override_until': zone.manual_override_until.isoformat() if zone.manual_override_until else None
        })

    @action(detail=True, methods=['post'])
    def dispatch_alert(self, request, pk=None):
        """
        Manually trigger an alert to all subscribed users in a zone.
        Only accessible by EmergencyTeam or admin users.

        POST data:
        - channels: list of channels to use ['sms', 'email'] (default: ['sms'])
        - test_message: custom message override (optional)
        - test_mode: if true, only shows what would happen without actually sending (default: false)
        """
        zone = self.get_object()

        # Permission check: only EmergencyTeam or admin
        if not (request.user.groups.filter(name='EmergencyTeam').exists() or request.user.is_superuser):
            return Response({'detail': 'Forbidden: EmergencyTeam or admin privileges required'},
                          status=status.HTTP_403_FORBIDDEN)

        # Parse request data
        channels = request.data.get('channels', ['sms'])
        test_message = request.data.get('test_message', '')
        test_mode = request.data.get('test_mode', False)

        # Validate channels
        valid_channels = ['sms', 'email']
        if not isinstance(channels, list):
            channels = [channels]
        channels = [c for c in channels if c in valid_channels]

        if not channels:
            return Response({'error': 'At least one valid channel required (sms, email)'},
                          status=status.HTTP_400_BAD_REQUEST)

        # Collect users in this zone
        from django.contrib.gis.geos import GEOSGeometry
        zone_polygon = zone.polygon

        # Find users with profiles having phone/email and within the zone
        from core.models import UserProfile
        profiles = UserProfile.objects.filter(
            user__is_active=True,
            sms_enabled=True
        ).select_related('user')

        # Filter users whose location is within the zone polygon (if they have location)
        target_users = []
        for profile in profiles:
            if profile.location and profile.location.within(zone_polygon):
                target_users.append(profile.user)
            # Also include users with no location (fallback to zone-based subscription)
            elif not profile.location:
                # In production, you'd have a ZoneSubscription model
                # For now, include all verified profiles
                if profile.phone_verified:
                    target_users.append(profile.user)

        # Build alert message
        message = test_message if test_message else (
            f"MANUAL ALERT: {zone.name} - Risk level: {zone.risk_score:.2f}. "
            f"Status: {'OVERRIDE ACTIVE' if zone.is_override_active else 'Normal monitoring'}"
        )

        if test_mode:
            # Return preview without sending
            return Response({
                'status': 'preview',
                'zone': zone.name,
                'channels': channels,
                'target_user_count': len(target_users),
                'message': message,
                'note': 'Test mode - no messages actually sent. Set test_mode=false to dispatch.'
            })

        # Trigger actual alert dispatch using existing task
        try:
            from core.tasks import dispatch_manual_alert

            # Use async task for dispatch
            task = dispatch_manual_alert.delay(
                zone_id=zone.id,
                user_ids=[u.id for u in target_users],
                channels=channels,
                message=message
            )

            return Response({
                'status': 'dispatched',
                'zone': zone.name,
                'channels': channels,
                'target_user_count': len(target_users),
                'task_id': task.id,
                'message': message
            })
        except Exception as e:
            return Response({
                'error': f'Failed to dispatch alert: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FloodReadingViewSet(viewsets.ModelViewSet):
    queryset = FloodReading.objects.all().order_by('-timestamp')
    serializer_class = FloodReadingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = None

    def get_queryset(self):
        """Optimize readings query with filtering by bbox, time range, and limit."""
        queryset = FloodReading.objects.all().order_by('-timestamp')

        # Bounding box filter
        bbox_param = self.request.query_params.get('bbox')
        if bbox_param:
            try:
                coords = [float(c) for c in bbox_param.split(',')]
                if len(coords) == 4:
                    min_lon, min_lat, max_lon, max_lat = coords
                    bbox_polygon = Polygon.from_bbox((min_lon, min_lat, max_lon, max_lat))
                    queryset = queryset.filter(location__intersects=bbox_polygon)
            except (ValueError, TypeError):
                pass

        # Time range filter (last N hours)
        hours_param = self.request.query_params.get('hours')
        if hours_param:
            try:
                hours = int(hours_param)
                if hours > 0:
                    cutoff = timezone.now() - datetime.timedelta(hours=hours)
                    queryset = queryset.filter(timestamp__gte=cutoff)
            except ValueError:
                pass

        # Limit results (max 500, default 200)
        limit = self.request.query_params.get('limit')
        if limit:
            try:
                limit_val = int(limit)
                if 0 < limit_val <= 500:
                    queryset = queryset[:limit_val]
            except ValueError:
                pass
        else:
            queryset = queryset[:200]

        return queryset

    @action(detail=False, methods=['get'])
    def predict(self, request):
        """
        Custom action to predict risk score for a zone.
        Expects zone_id and hours_ahead as query parameters.
        """
        zone_id = request.query_params.get('zone_id')
        hours_ahead = request.query_params.get('hours_ahead', 8)

        if not zone_id:
            return Response({'error': 'zone_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from core.analytics.scoring import calculate_risk_score
            risk_score = calculate_risk_score(int(zone_id))
            return Response({'risk_score': risk_score})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def heatmap(self, request):
        """
        Return heatmap data: points with risk intensity for visualization.
        Supports bbox and time filtering.
        """
        # Get latest readings within optional bbox and time window
        queryset = self.get_queryset()
        # Only readings with risk_score
        queryset = queryset.filter(risk_score__isnull=False).order_by('-timestamp')
        
        data = []
        for reading in queryset[:500]:  # Cap at 500 points for performance
            if reading.location:
                data.append({
                    'lat': reading.location.y,
                    'lng': reading.location.x,
                    'intensity': float(reading.risk_score),
                    'timestamp': reading.timestamp.isoformat(),
                    'water_level': reading.water_level_metres,
                })
        
        return Response({'heatmap': data})


class IncidentReportViewSet(viewsets.ModelViewSet):
    queryset = IncidentReport.objects.all().select_related('submitted_by', 'reviewed_by', 'acknowledged_by').order_by('-created_at')
    serializer_class = IncidentReportSerializer

    def get_queryset(self):
        queryset = IncidentReport.objects.all().select_related('submitted_by', 'reviewed_by', 'acknowledged_by').order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        submitted_by = self.request.query_params.get('submitted_by')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if submitted_by == 'me':
            if not self.request.user.is_authenticated:
                return queryset.none()
            queryset = queryset.filter(submitted_by=self.request.user)
        return queryset

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'create']:
            return [permissions.AllowAny()]
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated()]
        if self.action == 'verify':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(submitted_by=user)

    @action(detail=True, methods=['patch'])
    def verify(self, request, pk=None):
        report = self.get_object()
        if not request.user.groups.filter(name='EmergencyTeam').exists() and not request.user.is_superuser:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')
        if new_status not in ['verified', 'rejected']:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

        report.status = new_status
        report.reviewed_by = request.user
        report.save()
        return Response({'status': report.status})


class AlertLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AlertLog.objects.all().select_related('alert_zone').order_by('-triggered_at')
    serializer_class = AlertLogSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def stats_view(request):
    today = timezone.now().date()
    return Response({
        'zones_count': AlertZone.objects.count(),
        'alerts_today': AlertLog.objects.filter(triggered_at__date=today).count(),
        'reports_this_week': IncidentReport.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'high_risk_zones': AlertZone.objects.filter(risk_score__gt=0.7).count(),
    })


@require_http_methods(["GET"])
def health_view(request):
    redis_status = 'unknown'
    try:
        from core.tasks import redis_client
        redis_status = 'ok' if redis_client.ping() else 'down'
    except Exception:
        redis_status = 'down'

    return JsonResponse({
        'status': 'ok',
        'celery_status': 'unknown',
        'redis_status': redis_status,
        'last_poll_time': timezone.now().isoformat(),
    })

def landing_index(request):
    """Public landing page"""
    # Get active zones count for the hero section
    zones_count = AlertZone.objects.count()
    # Get recent high-risk zones for preview
    high_risk_zones = AlertZone.objects.filter(risk_score__gt=0.7)[:3]
    context = {
        'zones_count': zones_count,
        'high_risk_zones': high_risk_zones,
    }
    return render(request, 'landing/index.html', context)

def about(request):
    """About page"""
    return render(request, 'landing/about.html')

def login_view(request):
    """Login view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect based on user role
            if user.is_superuser:
                return redirect('admin_dashboard')
            elif user.groups.filter(name='EmergencyTeam').exists():
                return redirect('authority_dashboard')
            else:
                return redirect('citizen_dashboard')
        else:
            return render(request, 'auth/login.html', {'error': 'Invalid credentials'})
    return render(request, 'auth/login.html')

def register_view(request):
    """Registration view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        phone_number = request.POST.get('phone_number', '').strip()
        
        if password1 != password2:
            return render(request, 'auth/register.html', {'error': 'Passwords do not match'})
        
        if User.objects.filter(username=username).exists():
            return render(request, 'auth/register.html', {'error': 'Username already exists'})
        
        if User.objects.filter(email=email).exists():
            return render(request, 'auth/register.html', {'error': 'Email already exists'})
        
        # Validate phone number if provided
        if phone_number:
            cleaned = phone_number.replace(' ', '').replace('-', '')
            if not cleaned.startswith('+'):
                return render(request, 'auth/register.html', {
                    'error': 'Phone number must be in international format (e.g., +254712345678)'
                })
            digits = cleaned[1:]
            if not digits.isdigit() or not (10 <= len(digits) <= 15):
                return render(request, 'auth/register.html', {
                    'error': 'Phone number must be 10-15 digits after country code'
                })
        
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password1)
                # Ensure profile exists (signal should create it, but use get_or_create for safety)
                profile, created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={'role': 'citizen'}
                )
                if phone_number:
                    profile.phone_number = phone_number
                    profile.sms_enabled = True
                profile.save()
        except IntegrityError:
            return render(request, 'auth/register.html', {
                'error': 'Account creation could not be completed. Please try again.'
            })
        
        login(request, user)
        return redirect('citizen_dashboard')
    
    return render(request, 'auth/register.html')

def logout_view(request):
    """Logout view"""
    logout(request)
    return redirect('landing_index')

def dashboard_redirect(request):
    """Redirect to appropriate dashboard based on user role"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    elif request.user.groups.filter(name='EmergencyTeam').exists():
        return redirect('authority_dashboard')
    else:
        return redirect('citizen_dashboard')

@login_required
def citizen_dashboard(request):
    """Citizen dashboard"""
    UserProfile.objects.get_or_create(user=request.user, defaults={'role': 'citizen'})
    context = {
        'user': request.user,
    }
    return render(request, 'dashboard/public.html', context)

@login_required
def authority_dashboard(request):
    """Authority dashboard - requires EmergencyTeam group"""
    if not request.user.groups.filter(name='EmergencyTeam').exists():
        return redirect('login')
    
    context = {
        'user': request.user,
    }
    return render(request, 'dashboard/authority.html', context)

@login_required
def admin_dashboard(request):
    """Admin dashboard - superuser only"""
    if not request.user.is_superuser:
        return redirect('login')
    
    context = {
        'user': request.user,
    }
    return render(request, 'dashboard/admin_panel.html', context)

def report_submit(request):
    """Handle citizen report submission"""
    if request.method == 'POST':
        try:
            # Extract form data
            latitude = float(request.POST.get('latitude', 0))
            longitude = float(request.POST.get('longitude', 0))
            severity = int(request.POST.get('severity', 1))
            description = request.POST.get('description', '')
            
            # Validate severity range
            if severity < 1 or severity > 5:
                raise ValueError("Severity must be between 1 and 5")
            
            # Validate description length
            if len(description) < 10:
                raise ValueError("Description must be at least 10 characters")
            
            # Validate coordinates within configured geographic bounds
            bounds = getattr(settings, 'DEFAULT_GEO_BOUNDS', [33.0, -5.0, 42.0, 5.0])
            if len(bounds) == 4:
                min_lon, min_lat, max_lon, max_lat = bounds
                if not (min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat):
                    raise ValueError(f"Location outside supported area (bounds: {bounds})")
            
            # Create point
            location = Point(longitude, latitude, srid=4326)
            
            # Create report
            report = IncidentReport.objects.create(
                location=location,
                severity=severity,
                description=description,
                submitted_by=request.user if request.user.is_authenticated else None
            )
            
            # Handle photo upload if present
            if 'photo' in request.FILES:
                photo = request.FILES['photo']
                # Validate file size (max 5MB)
                if photo.size > 5 * 1024 * 1024:
                    raise ValueError("Photo must be under 5MB")
                report.photo = photo
                report.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'report_id': report.id})
            else:
                return render(request, 'reports/submit.html', {
                    'success': True,
                    'report_id': report.id
                })
                
        except ValueError as e:
            error_msg = str(e)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg})
            else:
                return render(request, 'reports/submit.html', {
                    'error': error_msg
                })
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'An unexpected error occurred'})
            else:
                return render(request, 'reports/submit.html', {
                    'error': 'An unexpected error occurred. Please try again.'
                })
    
    # GET request - show form
    return render(request, 'reports/submit.html')

def report_list(request):
    """List all reports"""
    reports = IncidentReport.objects.select_related(
        'submitted_by', 
        'reviewed_by',
        'acknowledged_by'
    ).all().order_by('-created_at')
    context = {
        'reports': reports,
    }
    return render(request, 'reports/list.html', context)

def alert_history(request):
    """Alert history view"""
    alerts = AlertLog.objects.select_related('alert_zone').all().order_by('-triggered_at')
    context = {
        'alerts': alerts,
    }
    return render(request, 'alerts/history.html', context)

def map_view(request):
    """Full screen map view"""
    zones = AlertZone.objects.all().only('id', 'name', 'polygon', 'risk_score', 'risk_threshold')
    context = {
        'zones': zones,
    }
    return render(request, 'map.html', context)

# API endpoints for dashboard data
@require_http_methods(["GET"])
def api_zone_status(request):
    """API endpoint for zone status data"""
    zones = AlertZone.objects.all()
    zones_data = []
    for zone in zones:
        zones_data.append({
            'id': zone.id,
            'name': zone.name,
            'risk_threshold': zone.risk_threshold,
            'manual_override_active': zone.manual_override_active,
        })
    return JsonResponse({'zones': zones_data})

@require_http_methods(["GET"])
def api_recent_alerts(request):
    """API endpoint for recent alerts"""
    alerts = AlertLog.objects.select_related('alert_zone').order_by('-triggered_at')[:10]
    alerts_data = []
    for alert in alerts:
        alerts_data.append({
            'id': alert.id,
            'message': alert.message,
            'zone_name': alert.alert_zone.name,
            'channel': alert.channel,
            'triggered_at': alert.triggered_at.isoformat(),
            'delivery_status': alert.delivery_status,
        })
    return JsonResponse({'alerts': alerts_data})

@require_http_methods(["GET"])
def api_dashboard_stats(request):
    """API endpoint for dashboard statistics"""
    from django.utils import timezone
    from datetime import timedelta
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    
    stats = {
        'total_zones': AlertZone.objects.count(),
        'alerts_today': AlertLog.objects.filter(triggered_at__gte=today_start).count(),
        'reports_this_week': IncidentReport.objects.filter(created_at__gte=week_start).count(),
        'high_risk_zones': AlertZone.objects.filter(risk_threshold__gte=0.7).count(),
    }
    return JsonResponse(stats)
