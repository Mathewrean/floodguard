from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from .models import AlertZone, FloodReading, IncidentReport, AlertLog
from .serializers import AlertZoneSerializer, FloodReadingSerializer, IncidentReportSerializer, AlertLogSerializer
from .permissions import IsAuthority, IsAdminUser
from .analytics.scoring import calculate_risk_score


class AlertZoneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AlertZone.objects.all()
    serializer_class = AlertZoneSerializer
    permission_classes = [AllowAny]  # Public endpoint


class FloodReadingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FloodReading.objects.all().order_by('-timestamp')[:100]  # Latest 100
    serializer_class = FloodReadingSerializer
    permission_classes = [IsAuthority]  # Authority or admin only

    @action(detail=False, methods=['get'])
    def predict(self, request):
        """
        Predict risk score for a given zone and time horizon.
        """
        zone_id = request.query_params.get('zone_id')
        hours_ahead = request.query_params.get('hours_ahead', 8)
        
        if not zone_id:
            return Response({'error': 'zone_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Calculate risk score using our scoring function
            risk_score = calculate_risk_score(int(zone_id))
            return Response({'risk_score': risk_score})
        except ValueError:
            return Response({'error': 'Invalid zone_id'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IncidentReportViewSet(viewsets.ModelViewSet):
    queryset = IncidentReport.objects.all()
    serializer_class = IncidentReportSerializer

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [AllowAny]  # Public submission
        elif self.action == 'list':
            permission_classes = [IsAuthority]  # Authority or admin to list all reports
        elif self.action == 'verify':
            permission_classes = [IsAuthority]  # Authority or admin to verify
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    @action(detail=True, methods=['patch'])
    def verify(self, request, pk=None):
        # Placeholder for verification - to be implemented in Phase 4
        report = self.get_object()
        status_val = request.data.get('status')
        if status_val not in dict(IncidentReport.STATUS_CHOICES):
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        report.status = status_val
        report.reviewed_by = request.user
        report.save()
        serializer = self.get_serializer(report)
        return Response(serializer.data)


class AlertLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AlertLog.objects.all()
    serializer_class = AlertLogSerializer
    permission_classes = [IsAuthority]

    @action(detail=False, methods=['post'])
    def send(self, request):
        """
        Manually trigger alert dispatch for testing (admin only).
        """
        # Only allow admin users to manually trigger alerts
        if not request.user.is_superuser:
            return Response({'error': 'Only admins can manually trigger alerts'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        zone_id = request.data.get('zone_id')
        risk_score = request.data.get('risk_score', 0.8)
        
        if not zone_id:
            return Response({'error': 'zone_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Trigger the Celery task
            from core.tasks import dispatch_alerts
            dispatch_alerts.delay(int(zone_id), float(risk_score))
            return Response({'status': 'Alert dispatch triggered'})
        except ValueError:
            return Response({'error': 'Invalid zone_id or risk_score'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)