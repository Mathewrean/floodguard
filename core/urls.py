from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import AlertZoneViewSet, FloodReadingViewSet, IncidentReportViewSet, AlertLogViewSet

router = DefaultRouter()
router.register(r'zones', AlertZoneViewSet)
router.register(r'readings', FloodReadingViewSet)
router.register(r'reports', IncidentReportViewSet)
router.register(r'alerts', AlertLogViewSet, basename='alert')

urlpatterns = [
    path('api/v1/', include(router.urls)),
]