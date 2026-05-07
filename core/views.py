from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
from .models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile
from django.contrib.gis.geos import Point
from datetime import timedelta
from django.utils import timezone

# REST API imports
from rest_framework import viewsets, permissions, status, serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_gis.serializers import GeometryField

# Serializers for API
class AlertZoneSerializer(drf_serializers.ModelSerializer):
    polygon = GeometryField()

    class Meta:
        model = AlertZone
        fields = ['id', 'name', 'risk_threshold', 'manual_override_active', 'manual_override_until', 'polygon']

class FloodReadingSerializer(drf_serializers.ModelSerializer):
    location = drf_serializers.SerializerMethodField()

    class Meta:
        model = FloodReading
        fields = ['id', 'location', 'water_level_metres', 'risk_score', 'source', 'verified', 'timestamp']

    def get_location(self, obj):
        if obj.location:
            return [obj.location.x, obj.location.y]
        return None

class IncidentReportSerializer(drf_serializers.ModelSerializer):
    location = GeometryField()
    photo = drf_serializers.ImageField(write_only=True, required=False, allow_null=True)
    photo_url = drf_serializers.SerializerMethodField()
    submitted_by = drf_serializers.SerializerMethodField()
    reviewed_by = drf_serializers.SerializerMethodField()

    class Meta:
        model = IncidentReport
        fields = ['id', 'location', 'severity', 'description', 'photo', 'photo_url', 'status', 'submitted_by', 'reviewed_by', 'created_at', 'updated_at']

    def get_photo_url(self, obj):
        if obj.photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.photo.url)
            return obj.photo.url
        return None

    def get_submitted_by(self, obj):
        if obj.submitted_by:
            return obj.submitted_by.username
        return None

    def get_reviewed_by(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.username
        return None

    def validate_location(self, value):
        # Validate location is within supported region (Kenya/East Africa bounds)
        lon = value.x
        lat = value.y
        # Kenya approximate bounds: longitude 33.0 to 42.0, latitude -5.0 to 5.0
        if not (33.0 <= lon <= 42.0 and -5.0 <= lat <= 5.0):
            raise drf_serializers.ValidationError("Location outside supported area")
        return value

class AlertLogSerializer(drf_serializers.ModelSerializer):
    zone_name = drf_serializers.SerializerMethodField()

    class Meta:
        model = AlertLog
        fields = ['id', 'zone_name', 'message', 'channel', 'recipient_count', 'triggered_at', 'delivery_status']

    def get_zone_name(self, obj):
        return obj.alert_zone.name

# ViewSets
class AlertZoneViewSet(viewsets.ModelViewSet):
    queryset = AlertZone.objects.all()
    serializer_class = AlertZoneSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = None  # Return list directly

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

class FloodReadingViewSet(viewsets.ModelViewSet):
    queryset = FloodReading.objects.all()
    serializer_class = FloodReadingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = None

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

class IncidentReportViewSet(viewsets.ModelViewSet):
    queryset = IncidentReport.objects.all()
    serializer_class = IncidentReportSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

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
    queryset = AlertLog.objects.all().select_related('alert_zone')
    serializer_class = AlertLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

def landing_index(request):
    """Public landing page"""
    # Get active zones count for the hero section
    zones_count = AlertZone.objects.count()
    context = {
        'zones_count': zones_count,
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
        
        if password1 != password2:
            return render(request, 'auth/register.html', {'error': 'Passwords do not match'})
        
        if User.objects.filter(username=username).exists():
            return render(request, 'auth/register.html', {'error': 'Username already exists'})
        
        if User.objects.filter(email=email).exists():
            return render(request, 'auth/register.html', {'error': 'Email already exists'})
        
        user = User.objects.create_user(username=username, email=email, password=password1)
        # Add default citizen profile
        from .models import UserProfile
        UserProfile.objects.create(user=user, role='citizen')
        
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
    # Get user's location and zone info
    user_profile = request.user.profile
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
                report.photo = request.FILES['photo']
                report.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'report_id': report.id})
            else:
                return render(request, 'reports/submit.html', {
                    'success': True,
                    'report_id': report.id
                })
                
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            else:
                return render(request, 'reports/submit.html', {
                    'error': str(e)
                })
    
    # GET request - show form
    return render(request, 'reports/submit.html')

def report_list(request):
    """List all reports"""
    reports = IncidentReport.objects.all().order_by('-created_at')
    context = {
        'reports': reports,
    }
    return render(request, 'reports/list.html', context)

def alert_history(request):
    """Alert history view"""
    alerts = AlertLog.objects.all().order_by('-triggered_at')
    context = {
        'alerts': alerts,
    }
    return render(request, 'alerts/history.html', context)

def map_view(request):
    """Full screen map view"""
    zones = AlertZone.objects.all()
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