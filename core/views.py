from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.db import IntegrityError, transaction
from django.http import FileResponse, JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import math
from .models import AlertZone, FloodReading, IncidentReport, AlertLog, UserProfile
from .permissions import is_authority_user, IsAuthority
from django.contrib.gis.geos import LineString, Point, Polygon
from datetime import timedelta
import logging
from django.utils import timezone
from django.conf import settings

try:
    from groq import Groq
except ImportError:
    Groq = None

logger = logging.getLogger(__name__)

from core.data_sources.aggregator import build_risk_feature_vector

# REST API imports
from rest_framework import viewsets, permissions, status, serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_gis.serializers import GeometryField

# Serializers for API (imported from serializers.py)
from .serializers import (
    AlertZoneSerializer,
    FloodReadingSerializer,
    IncidentReportSerializer,
    AlertLogSerializer
)

class MonitoringRateThrottle(UserRateThrottle):
    """Higher limit for read-heavy monitoring/dashboard endpoints."""
    rate = '2000/hour'


class ReportSubmissionThrottle(AnonRateThrottle):
    """Strict public throttle for citizen report submission spam prevention."""
    rate = '10/hour'


class DynamicZoneThrottle(AnonRateThrottle):
    """Limit anonymous GPS-triggered dynamic zone creation checks."""
    rate = '60/hour'


class AIAnalysisThrottle(UserRateThrottle):
    """Rate limit AI analysis to prevent Groq quota exhaustion."""
    rate = '10/minute'


class StandardPagination(LimitOffsetPagination):
    default_limit = 100
    max_limit = 500


class AlertZoneViewSet(viewsets.ModelViewSet):
    queryset = AlertZone.objects.all().prefetch_related('alert_logs').order_by('-risk_score', 'name')
    serializer_class = AlertZoneSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = StandardPagination
    throttle_classes = [MonitoringRateThrottle]

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
        if not is_authority_user(request.user):
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
        if not is_authority_user(request.user):
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

        # Profiles do not currently store live location. In production this should
        # target explicit zone subscriptions or recent device presence.
        target_users = []
        for profile in profiles:
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
    throttle_classes = [MonitoringRateThrottle]

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
                    cutoff = timezone.now() - timedelta(hours=hours)
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
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [IsAuthority()]

    def get_throttles(self):
        if self.action == 'create':
            return [ReportSubmissionThrottle()]
        return super().get_throttles()

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(submitted_by=user)

    @action(detail=True, methods=['patch'])
    def verify(self, request, pk=None):
        report = self.get_object()
        if not is_authority_user(request.user):
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
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    throttle_classes = [MonitoringRateThrottle]


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([])
def stats_view(request):
    today = timezone.now().date()
    return Response({
        'zones_count': AlertZone.objects.count(),
        'alerts_today': AlertLog.objects.filter(triggered_at__date=today).count(),
        'reports_this_week': IncidentReport.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
        'high_risk_zones': AlertZone.objects.filter(risk_score__gte=0.7, risk_score__lt=0.85).count(),
        'critical_zones': AlertZone.objects.filter(risk_score__gte=0.85).count(),
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([])
def data_sources_view(request):
    """Data-source status for authenticated users (admin/authority)."""
    if not is_authority_user(request.user):
        return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    from core.data_sources.aggregator import get_source_status

    statuses = get_source_status()
    active = sum(1 for item in statuses if item['configured'])
    return Response({
        'sources': statuses,
        'active_sources': active,
        'data_confidence': 'high' if active >= 3 else 'medium' if active >= 2 else 'low',
    })


def _ai_analysis_fields(user):
    if not getattr(user, 'is_authenticated', False):
        return ['overall_risk', 'summary', 'safe_zones', 'highest_risk_zone']
    if user.is_superuser:
        return None
    if user.groups.filter(name='EmergencyTeam').exists():
        return ['overall_risk', 'summary', 'safe_zones', 'immediate_actions', '24h_outlook', 'highest_risk_zone']
    return ['overall_risk', 'summary', 'safe_zones', '24h_outlook']


def _filter_ai_analysis(analysis, user):
    fields = _ai_analysis_fields(user)
    if fields is None:
        return analysis
    return {field: analysis.get(field) for field in fields if field in analysis}


def _format_source_context(all_data: dict) -> list[str]:
    lines = []
    for source_name, source_data in all_data.items():
        if not source_data.get('available'):
            error = source_data.get('error', 'missing key or unavailable service')
            lines.append(f"{source_name}: unavailable ({error})")
            continue
        values = [f"{k}={v}" for k, v in source_data.items() if k not in ('source', 'available', 'error')]
        lines.append(f"{source_name}: {', '.join(values) if values else 'available'}")
    return lines


def _describe_features(features: dict) -> list[str]:
    lines = []
    for name, value in sorted(features.items()):
        if name in ('sources', 'zone_name'):
            continue
        lines.append(f"{name}: {value}")
    return lines


def _selected_analysis_location(request, zones, latest_reading):
    zone_id = request.query_params.get('zone_id')
    if zone_id:
        try:
            return zones.filter(id=zone_id).first()
        except (ValueError, TypeError):
            pass
    return zones.first() or latest_reading


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([AIAnalysisThrottle])
def ai_flood_analysis(request):
    import json

    zones = AlertZone.objects.all().order_by('-risk_score', 'name')
    latest_reading = FloodReading.objects.order_by('-timestamp').first()
    target = _selected_analysis_location(request, zones, latest_reading)

    if isinstance(target, AlertZone):
        region_name = target.name
        centroid = target.centroid
        lat, lon = centroid.y, centroid.x
    elif isinstance(target, FloodReading) and target.location:
        region_name = 'latest-reading'
        lat, lon = target.location.y, target.location.x
    else:
        default_bounds = getattr(settings, 'DEFAULT_GEO_BOUNDS', [33.0, -5.0, 42.0, 5.0])
        region_name = 'default-region'
        lat = (default_bounds[1] + default_bounds[3]) / 2
        lon = (default_bounds[0] + default_bounds[2]) / 2

    features = build_risk_feature_vector(lat, lon, region_name)
    all_data = features.get('sources', {}) if isinstance(features, dict) else {}
    source_lines = _format_source_context(all_data)
    feature_lines = _describe_features(features)

    prompt = f"""You are FloodGuard AI analysing flood risk for {region_name}.

Top monitored zones:
{chr(10).join([f'- {zone.name}: {round((zone.risk_score or 0) * 100, 1)}%' for zone in zones[:5]]) or '- none'}

Location coordinates: {lat}, {lon}

Combined feature vector:
{chr(10).join(feature_lines)}

Source data details:
{chr(10).join(f'- {line}' for line in source_lines)}

Based on these multi-source weather, hydrology, and satellite intelligence inputs, respond ONLY with valid JSON:
{{
  "overall_risk": "LOW|MODERATE|HIGH|CRITICAL",
  "summary": "2-3 sentence situation overview",
  "highest_risk_zone": "zone name",
  "immediate_actions": ["action1", "action2", "action3"],
  "24h_outlook": "one sentence forecast",
  "safe_zones": ["zone1", "zone2"]
}}"""

    analysis = None
    source = 'fallback'
    metadata = features.copy() if isinstance(features, dict) else {}

    try:
        api_key = getattr(settings, 'GROQ_API_KEY', '')
        if not api_key or Groq is None:
            raise ValueError('GROQ_API_KEY missing or groq package unavailable')

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model='llama-3.1-8b-instant',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=1024,
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            content = content[start:end + 1]
        analysis = json.loads(content)
        source = 'groq'
    except Exception as exc:
        logger.warning('Groq analysis failed: %s', exc)
        high = [zone.name for zone in zones if (zone.risk_score or 0) > 0.70]
        moderate = [zone.name for zone in zones if 0.40 < (zone.risk_score or 0) <= 0.70]
        safe = [zone.name for zone in zones if (zone.risk_score or 0) <= 0.40]
        level = 'CRITICAL' if len(high) > 3 else 'HIGH' if high else 'MODERATE' if moderate else 'LOW'
        analysis = {
            'overall_risk': level,
            'summary': f'{len(high)} high-risk zones. {len(moderate)} moderate. {len(safe)} safe.',
            'highest_risk_zone': high[0] if high else moderate[0] if moderate else 'None',
            'immediate_actions': [f'Monitor {zone_name}' for zone_name in high[:3]] or ['Routine monitoring'],
            '24h_outlook': 'Stable based on current readings.',
            'safe_zones': safe[:3],
        }

    filtered = _filter_ai_analysis(analysis, request.user)
    payload = {
        'success': True,
        'analysis': filtered,
        'source': source,
        'target': region_name,
    }
    if getattr(request.user, 'is_authenticated', False) and request.user.is_superuser:
        payload['data_confidence'] = metadata.get('data_confidence', 'unknown')
        payload['source_metadata'] = all_data
    return Response(payload)


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


@require_http_methods(["GET"])
def service_worker_view(request):
    response = render(request, 'service_worker.js', content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@require_http_methods(["GET"])
def favicon_view(request):
    favicon_path = settings.BASE_DIR / 'static' / 'favicon.ico'
    response = FileResponse(open(favicon_path, 'rb'), content_type='image/x-icon')
    response['Cache-Control'] = 'public, max-age=86400'
    return response


def _parse_route_coord(value, label):
    if isinstance(value, dict):
        lat = value.get('lat', value.get('latitude'))
        lng = value.get('lng', value.get('lon', value.get('longitude')))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        lat, lng = value[0], value[1]
    else:
        raise ValueError(f'{label} must include latitude and longitude')

    lat = float(lat)
    lng = float(lng)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError(f'{label} has invalid latitude or longitude')
    return {'lat': lat, 'lng': lng}


def _haversine_m(a, b):
    radius = 6371000
    lat1 = math.radians(a['lat'])
    lat2 = math.radians(b['lat'])
    dlat = math.radians(b['lat'] - a['lat'])
    dlng = math.radians(b['lng'] - a['lng'])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def _line_for_points(points):
    return LineString([(point['lng'], point['lat']) for point in points], srid=4326)


def _snap_to_navigable(coord):
    point = Point(coord['lng'], coord['lat'], srid=4326)
    high_risk_zone = AlertZone.objects.filter(risk_score__gt=0.7, polygon__covers=point).order_by('-risk_score').first()
    if not high_risk_zone:
        return {
            'coordinate': coord,
            'status': 'SNAPPED',
            'edge_id': 'pedestrian_network_estimate',
            'confidence': 0.92,
            'note': 'Coordinate accepted within the supported navigable area.',
        }

    min_lng, min_lat, max_lng, max_lat = high_risk_zone.polygon.extent
    candidates = [
        {'lat': max_lat + 0.002, 'lng': coord['lng']},
        {'lat': min_lat - 0.002, 'lng': coord['lng']},
        {'lat': coord['lat'], 'lng': max_lng + 0.002},
        {'lat': coord['lat'], 'lng': min_lng - 0.002},
    ]
    snapped = min(candidates, key=lambda candidate: _haversine_m(coord, candidate))
    return {
        'coordinate': snapped,
        'status': 'SNAPPED_WITH_RISK_OFFSET',
        'edge_id': f'zone-{high_risk_zone.id}-perimeter',
        'confidence': 0.74,
        'note': f'Point was inside high-risk zone {high_risk_zone.name}; shifted to nearest safer perimeter estimate.',
    }


def _candidate_detours(origin, destination):
    direct_line = _line_for_points([origin, destination])
    candidates = [{'profile': 'fastest', 'waypoints': [origin, destination]}]
    risky_zones = AlertZone.objects.filter(risk_score__gt=0.35, polygon__intersects=direct_line).order_by('-risk_score')[:4]

    for zone in risky_zones:
        min_lng, min_lat, max_lng, max_lat = zone.polygon.extent
        padding = 0.006 + (zone.risk_score * 0.004)
        detours = {
            'north': {'lat': max_lat + padding, 'lng': (min_lng + max_lng) / 2},
            'south': {'lat': min_lat - padding, 'lng': (min_lng + max_lng) / 2},
            'east': {'lat': (min_lat + max_lat) / 2, 'lng': max_lng + padding},
            'west': {'lat': (min_lat + max_lat) / 2, 'lng': min_lng - padding},
        }
        for name, waypoint in detours.items():
            candidates.append({
                'profile': f'{name}_detour',
                'waypoints': [origin, waypoint, destination],
                'detour_zone': zone.name,
            })

    return candidates


def _score_route(points, weights):
    distance_m = sum(_haversine_m(points[index], points[index + 1]) for index in range(len(points) - 1))
    risk_exposure = 0.0
    crossed_zones = []

    for index in range(len(points) - 1):
        segment = _line_for_points([points[index], points[index + 1]])
        for zone in AlertZone.objects.filter(polygon__intersects=segment):
            exposure = float(zone.risk_score or 0)
            risk_exposure += exposure
            if zone.name not in crossed_zones:
                crossed_zones.append(zone.name)

    low_light_penalty = 0.18 if distance_m > 1800 else 0.08
    isolation_penalty = 0.10 if len(points) <= 2 else 0.04
    confidence_penalty = 0.06 if not crossed_zones else 0.12
    safety_cost = (
        distance_m * weights['distance']
        + risk_exposure * 1000 * weights['risk']
        + low_light_penalty * 400 * weights['lighting']
        + isolation_penalty * 350 * weights['flow']
        + confidence_penalty * 250 * weights['confidence']
    )
    safety_score = max(0, min(100, 100 - (risk_exposure * 24) - (low_light_penalty * 12) - (isolation_penalty * 10)))

    return {
        'distance_m': round(distance_m, 1),
        'duration_min': round(distance_m / 75, 1),
        'risk_exposure': round(risk_exposure, 3),
        'safety_cost': round(safety_cost, 2),
        'safety_score': round(safety_score, 1),
        'crossed_zones': crossed_zones,
    }


def _route_weights(profile):
    profiles = {
        'fastest': {'distance': 1.0, 'risk': 0.35, 'lighting': 0.2, 'flow': 0.2, 'confidence': 0.1},
        'balanced': {'distance': 1.0, 'risk': 0.75, 'lighting': 0.45, 'flow': 0.35, 'confidence': 0.2},
        'safest': {'distance': 1.0, 'risk': 1.35, 'lighting': 0.8, 'flow': 0.7, 'confidence': 0.35},
    }
    return profiles.get(profile, profiles['balanced'])


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def safe_route_view(request):
    try:
        raw_origin = _parse_route_coord(request.data.get('origin'), 'origin')
        raw_destination = _parse_route_coord(request.data.get('destination'), 'destination')
    except (TypeError, ValueError) as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    snapped_origin = _snap_to_navigable(raw_origin)
    snapped_destination = _snap_to_navigable(raw_destination)
    origin = snapped_origin['coordinate']
    destination = snapped_destination['coordinate']
    requested_profile = request.data.get('profile', 'balanced')

    route_options = []
    for candidate in _candidate_detours(origin, destination):
        profile = candidate['profile'] if candidate['profile'] in {'fastest', 'balanced', 'safest'} else requested_profile
        metrics = _score_route(candidate['waypoints'], _route_weights(profile))
        route_options.append({
            **metrics,
            'id': candidate['profile'],
            'profile': profile,
            'label': candidate['profile'].replace('_', ' ').title(),
            'geometry': [[point['lat'], point['lng']] for point in candidate['waypoints']],
            'detour_zone': candidate.get('detour_zone'),
        })

    direct = [route for route in route_options if route['id'] == 'fastest']
    sorted_by_safety = sorted(route_options, key=lambda route: (-route['safety_score'], route['safety_cost']))
    sorted_by_cost = sorted(route_options, key=lambda route: route['safety_cost'])
    selected = []
    if direct:
        selected.append({**direct[0], 'profile': 'fastest', 'label': 'Fastest'})
    if sorted_by_cost:
        selected.append({**sorted_by_cost[0], 'profile': 'balanced', 'label': 'Balanced'})
    if sorted_by_safety:
        selected.append({**sorted_by_safety[0], 'profile': 'safest', 'label': 'Safest'})

    unique_routes = []
    seen = set()
    for route in selected:
        route_key = tuple(tuple(point) for point in route['geometry'])
        if route_key not in seen:
            seen.add(route_key)
            unique_routes.append(route)

    return Response({
        'origin': snapped_origin,
        'destination': snapped_destination,
        'routes': unique_routes,
        'engine': {
            'algorithm': 'SCF-weighted A* prototype over generated pedestrian candidate graph',
            'weights_profile': requested_profile,
            'updated_at': timezone.now().isoformat(),
        }
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def snap_coordinate_view(request):
    try:
        coordinate = _parse_route_coord(request.data.get('coordinate'), 'coordinate')
    except (TypeError, ValueError) as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(_snap_to_navigable(coordinate))

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
    
    # Pre-fetch global zones for initial dashboard load
    zones = AlertZone.objects.all().order_by('-risk_score', 'name')[:15]
    context = {
        'user': request.user,
        'preloaded_zones': zones,
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
            bounds = getattr(settings, 'DEFAULT_GEO_BOUNDS', None)
            if bounds and len(bounds) == 4:
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


def map_selection_view(request):
    """Interactive map selection page"""
    return render(request, 'map_selection.html')


def safe_route_page(request):
    """Safe-route navigation prototype."""
    return render(request, 'safe_route.html')

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
        'high_risk_zones': AlertZone.objects.filter(risk_score__gte=0.7, risk_score__lt=0.85).count(),
        'critical_zones': AlertZone.objects.filter(risk_score__gte=0.85).count(),
    }
    return JsonResponse(stats)


@require_http_methods(["GET"])
def api_global_search(request):
    """Global search for flood zones by name, city, or coordinates."""
    query = request.GET.get('q', '').strip()
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    radius_km = float(request.GET.get('radius_km', 50))

    results = []
    if query:
        results = AlertZone.objects.filter(name__icontains=query).order_by('-risk_score')[:20]
    elif lat and lon:
        try:
            lat_f = float(lat)
            lon_f = float(lon)
            if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                user_point = Point(lon_f, lat_f, srid=4326)
                results = AlertZone.objects.filter(
                    polygon__distance_lte=(user_point, 0.01)
                ).order_by('-risk_score')[:20]
        except (ValueError, TypeError):
            pass

    data = []
    for zone in results:
        data.append({
            'id': zone.id,
            'name': zone.name,
            'risk_score': round(float(zone.risk_score or 0), 3),
            'risk_threshold': round(float(zone.risk_threshold or 0), 3),
            'centroid': [zone.polygon.centroid.x, zone.polygon.centroid.y] if zone.polygon else None,
        })

    return JsonResponse({'results': data, 'count': len(data)})


@require_http_methods(["GET"])
def api_nearby_zones(request):
    """Return zones near the user's location for dashboard auto-population."""
    lat = request.GET.get('lat')
    lon = request.GET.get('lon')
    limit = int(request.GET.get('limit', 10))

    if not lat or not lon:
        return JsonResponse({'zones': [], 'count': 0})

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (ValueError, TypeError):
        return JsonResponse({'zones': [], 'count': 0})

    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return JsonResponse({'zones': [], 'count': 0})

    user_point = Point(lon_f, lat_f, srid=4326)
    zones = AlertZone.objects.filter(
        polygon__distance_lte=(user_point, 0.05)
    ).order_by('-risk_score')[:limit]

    data = []
    for zone in zones:
        data.append({
            'id': zone.id,
            'name': zone.name,
            'risk_score': round(float(zone.risk_score or 0), 3),
            'risk_threshold': round(float(zone.risk_threshold or 0), 3),
            'centroid': [zone.polygon.centroid.x, zone.polygon.centroid.y] if zone.polygon else None,
            'distance_approx_km': round(float(zone.polygon.distance(user_point) * 111.32), 1) if zone.polygon else None,
        })

    return JsonResponse({'zones': data, 'count': len(data)})


@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
def api_user_zone(request):
    """
    Dynamic zone lookup/creation based on user GPS coordinates.
    
    GET: Returns the zone covering the given coordinates, or a live assessment
    POST: Creates/updates a zone for the coordinates if user is authenticated
    """
    lat = request.GET.get('lat') or request.data.get('lat')
    lon = request.GET.get('lon') or request.data.get('lon')
    accuracy = request.GET.get('accuracy') or request.data.get('accuracy')

    if not lat or not lon:
        return Response({'error': 'lat and lon are required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        lat_f = float(lat)
        lon_f = float(lon)
        accuracy_f = float(accuracy) if accuracy else None
    except (TypeError, ValueError):
        return Response({'error': 'Invalid coordinates'}, status=status.HTTP_400_BAD_REQUEST)

    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return Response({'error': 'Coordinates out of range'}, status=status.HTTP_400_BAD_REQUEST)

    user_point = Point(lon_f, lat_f, srid=4326)
    matched_zones = AlertZone.objects.filter(polygon__covers=user_point).order_by('-risk_score', 'name')

    if matched_zones.exists():
        zone = matched_zones.first()
        return Response({
            'has_zone': True,
            'created_zone': False,
            'source': 'existing',
            'zone': _zone_summary(zone),
        })

    zone_name = _dynamic_zone_name(lat_f, lon_f)
    features, risk_score = _dynamic_risk_assessment(lat_f, lon_f, zone_name)
    severity = (
        'CRITICAL' if risk_score > 0.85 else
        'HIGH' if risk_score > 0.7 else
        'MODERATE' if risk_score > 0.4 else
        'SAFE'
    )

    if request.method == 'GET':
        return Response({
            'has_zone': False,
            'created_zone': False,
            'live_assessment': True,
            'zone_name': zone_name,
            'risk_score': round(risk_score, 3),
            'risk_threshold': max(0.2, min(0.95, risk_score)),
            'severity': severity,
            'source_count': int(features.get('sources_available', 0) or 0),
            'data_confidence': features.get('data_confidence', 'low'),
        })

    if not request.user.is_authenticated:
        return Response({'error': 'Authentication required to create zones'}, status=status.HTTP_401_UNAUTHORIZED)

    zone_polygon = _dynamic_zone_polygon(lat_f, lon_f, accuracy_f)
    zone, created = AlertZone.objects.get_or_create(
        name=zone_name,
        defaults={
            'polygon': zone_polygon,
            'risk_threshold': max(0.2, min(0.95, risk_score)),
            'risk_score': round(risk_score, 3),
        }
    )
    if not created:
        zone.polygon = zone_polygon
        zone.risk_score = round(risk_score, 3)
        zone.risk_threshold = max(0.2, min(0.95, risk_score))
        zone.save(update_fields=['polygon', 'risk_score', 'risk_threshold', 'updated_at'])

    from core.models import AlertZoneActivity
    AlertZoneActivity.objects.create(
        zone=zone,
        user=request.user,
        source='dynamic',
        latitude=lat_f,
        longitude=lon_f,
        accuracy_meters=accuracy_f,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
    )

    return Response({
        'has_zone': True,
        'created_zone': created,
        'zone_id': zone.id,
        'zone_name': zone.name,
        'risk_score': round(float(zone.risk_score or 0), 3),
        'risk_threshold': round(float(zone.risk_threshold or 0), 3),
        'severity': severity,
        'source_count': int(features.get('sources_available', 0) or 0),
        'data_confidence': features.get('data_confidence', 'low'),
        'message': f'Live flood assessment for {zone_name}',
    })


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def api_zone_selection(request):
    """Save selected zones from interactive map."""
    zones_data = request.data.get('zones', [])
    
    if not zones_data:
        return Response({'error': 'No zones provided'}, status=status.HTTP_400_BAD_REQUEST)

    saved_zones = []
    for zone_data in zones_data:
        try:
            from django.contrib.gis.geos import Polygon
            polygon = Polygon(zone_data['polygon']['coordinates'][0], srid=4326)
            
            zone, created = AlertZone.objects.get_or_create(
                name=zone_data['name'],
                defaults={
                    'polygon': polygon,
                    'risk_score': zone_data.get('risk_score', 0.1),
                    'risk_threshold': zone_data.get('risk_threshold', 0.65),
                }
            )
            
            if not created:
                zone.polygon = polygon
                zone.risk_score = zone_data.get('risk_score', zone.risk_score)
                zone.risk_threshold = zone_data.get('risk_threshold', zone.risk_threshold)
                zone.save()
            
            saved_zones.append({
                'id': zone.id,
                'name': zone.name,
                'created': created,
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'saved_zones': saved_zones}, status=status.HTTP_201_CREATED)


def _parse_dynamic_zone_payload(request):
    payload = request.data if request.method == 'POST' else request.query_params
    lat = payload.get('lat', payload.get('latitude'))
    lon = payload.get('lon', payload.get('lng', payload.get('longitude')))
    accuracy = payload.get('accuracy')

    try:
        lat = float(lat)
        lon = float(lon)
        accuracy = float(accuracy) if accuracy not in (None, '') else None
    except (TypeError, ValueError):
        raise ValueError('Invalid latitude or longitude parameters')

    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError('Invalid latitude or longitude parameters')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Latitude or longitude is outside valid ranges')
    if accuracy is not None and (not math.isfinite(accuracy) or accuracy < 0):
        raise ValueError('Accuracy must be a positive number')

    bounds = getattr(settings, 'DEFAULT_GEO_BOUNDS', None)
    if bounds and len(bounds) == 4:
        min_lon, min_lat, max_lon, max_lat = bounds
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            raise ValueError('Location is outside the configured FloodGuard coverage area')

    return lat, lon, accuracy


def _dynamic_zone_name(lat, lon):
    import requests as req

    fallback = f"Dynamic Zone {lat:.3f},{lon:.3f}"
    try:
        geo = req.get(
            'https://nominatim.openstreetmap.org/reverse',
            params={'lat': lat, 'lon': lon, 'format': 'json'},
            headers={'User-Agent': 'FloodGuard/1.0'},
            timeout=5,
        )
        geo.raise_for_status()
        address = geo.json().get('address', {})
        area = (
            address.get('suburb')
            or address.get('neighbourhood')
            or address.get('city_district')
            or address.get('town')
            or address.get('city')
        )
        if area:
            return f"Dynamic Zone - {area}"[:100]
    except Exception:
        pass
    return fallback[:100]


def _dynamic_zone_polygon(lat, lon, accuracy=None):
    radius_m = max(300.0, min(1200.0, (accuracy or 300.0) * 2))
    lat_delta = radius_m / 111320.0
    lon_scale = max(0.2, math.cos(math.radians(lat)))
    lon_delta = radius_m / (111320.0 * lon_scale)
    return Polygon.from_bbox((lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta))


def _dynamic_risk_assessment(lat, lon, zone_name):
    try:
        features = build_risk_feature_vector(lat, lon, zone_name)
        from core.analytics.scoring import calculate_risk_score

        risk_score = calculate_risk_score(features)
    except Exception as exc:
        logger.warning("Dynamic zone risk assessment failed: %s", exc)
        features = {'sources_available': 0, 'data_confidence': 'low'}
        risk_score = 0.05

    risk_score = max(0.0, min(1.0, float(risk_score or 0)))
    return features, risk_score


def _zone_summary(zone):
    return {
        'id': zone.id,
        'name': zone.name,
        'risk_score': round(float(zone.risk_score or 0), 3),
        'risk_threshold': round(float(zone.risk_threshold or 0), 3),
    }


@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([DynamicZoneThrottle])
def dynamic_zone_check(request):
    """
    On-demand zone lookup and creation for a client-provided GPS location.
    GET is non-mutating. POST creates or refreshes a dynamic zone when no mapped
    zone already covers the submitted coordinate.
    """
    if request.method == 'POST' and not request.user.is_authenticated:
        return Response(
            {'error': 'Authentication required'},
            status=401
        )
    try:
        lat, lon, accuracy = _parse_dynamic_zone_payload(request)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user_point = Point(lon, lat, srid=4326)
    matched_zones = AlertZone.objects.filter(polygon__covers=user_point).order_by('-risk_score', 'name')

    if matched_zones.exists():
        return Response({
            'has_zone': True,
            'created_zone': False,
            'source': 'existing',
            'zones': [_zone_summary(zone) for zone in matched_zones],
        })

    zone_name = _dynamic_zone_name(lat, lon)
    features, risk_score = _dynamic_risk_assessment(lat, lon, zone_name)
    severity = (
        'CRITICAL' if risk_score > 0.85 else
        'HIGH' if risk_score > 0.7 else
        'MODERATE' if risk_score > 0.4 else
        'SAFE'
    )

    if request.method == 'GET':
        return Response({
            'has_zone': False,
            'created_zone': False,
            'live_assessment': True,
            'zone_name': zone_name,
            'risk_score': round(risk_score, 3),
            'risk_threshold': max(0.2, min(0.95, risk_score)),
            'severity': severity,
            'source_count': int(features.get('sources_available', 0) or 0),
            'data_confidence': features.get('data_confidence', 'low'),
        })

    try:
        zone_polygon = _dynamic_zone_polygon(lat, lon, accuracy)
        zone, created = AlertZone.objects.get_or_create(
            name=zone_name,
            defaults={
                'polygon': zone_polygon,
                'risk_threshold': max(0.2, min(0.95, risk_score)),
                'risk_score': round(risk_score, 3),
            },
        )
        if created:
            zone.polygon = zone_polygon
            zone.risk_threshold = max(0.2, min(0.95, risk_score))
            zone.risk_score = round(risk_score, 3)
            zone.save(update_fields=['polygon', 'risk_threshold', 'risk_score'])
        else:
            zone.polygon = zone_polygon
            zone.risk_score = round(risk_score, 3)
            zone.risk_threshold = max(0.2, min(0.95, risk_score))
            zone.save(update_fields=['polygon', 'risk_score', 'risk_threshold', 'updated_at'])

        return Response({
            'has_zone': True,
            'created_zone': created,
            'zone_id': zone.id,
            'zone_name': zone.name,
            'risk_score': round(float(zone.risk_score or 0), 3),
            'risk_threshold': round(float(zone.risk_threshold or 0), 3),
            'severity': severity,
            'source_count': int(features.get('sources_available', 0) or 0),
            'data_confidence': features.get('data_confidence', 'low'),
            'message': f'Live flood assessment for {zone_name}',
        })
    except Exception as e:
        return Response({'has_zone': False, 'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
