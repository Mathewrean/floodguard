from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from .models import AlertZone, FloodReading, IncidentReport, AlertLog
from .serializers import AlertZoneSerializer, FloodReadingSerializer, IncidentReportSerializer, AlertLogSerializer


class AlertZoneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AlertZone.objects.all()
    serializer_class = AlertZoneSerializer
    permission_classes = [AllowAny]  # Public endpoint


class FloodReadingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FloodReading.objects.all().order_by('-timestamp')[:100]  # Latest 100
    serializer_class = FloodReadingSerializer
    permission_classes = [IsAuthenticated]  # Token-authenticated


class IncidentReportViewSet(viewsets.ModelViewSet):
    queryset = IncidentReport.objects.all()
    serializer_class = IncidentReportSerializer

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [AllowAny]  # Public submission
        elif self.action == 'list':
            permission_classes = [IsAuthenticated]  # Authenticated to list
        elif self.action == 'verify':
            # Will be handled by a custom permission in Phase 4
            permission_classes = [IsAuthenticated]  # Placeholder
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
    permission_classes = [IsAuthenticated]