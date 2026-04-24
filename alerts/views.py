from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import FloodAlert
from .serializers import FloodAlertSerializer
from django.http import JsonResponse
# ...existing code...

class AlertListView(APIView):
    """
    List all flood alerts
    """
    def get(self, request):
        alerts = FloodAlert.objects.all().order_by('-triggered_at')[:10]
        serializer = FloodAlertSerializer(alerts, many=True)
        return Response({"alerts": serializer.data}, status=status.HTTP_200_OK)

class AlertDetailView(APIView):
    """
    Retrieve a single flood alert
    """
    def get(self, request, pk):
        try:
            alert = FloodAlert.objects.get(pk=pk)
            serializer = FloodAlertSerializer(alert)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except FloodAlert.DoesNotExist:
            return Response({"error": "Alert not found"}, status=status.HTTP_404_NOT_FOUND)

# Existing functions
def health_check(request):
    return JsonResponse({"status": "alerts ok"})

def alerts_api(request):
    alerts = FloodAlert.objects.order_by('-triggered_at')[:10]
    data = [
        {
            "title": f"{a.parameter} Threshold Exceeded",
            "location": a.location,
            "alert_level": a.severity,
            "created_at": a.triggered_at,
        } for a in alerts
    ]
    return JsonResponse({"alerts": data})
