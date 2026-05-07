from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views
from .views import AlertZoneViewSet, FloodReadingViewSet, IncidentReportViewSet, AlertLogViewSet

router = DefaultRouter()
router.register(r'zones', AlertZoneViewSet)
router.register(r'readings', FloodReadingViewSet)
router.register(r'reports', IncidentReportViewSet)
router.register(r'alerts', AlertLogViewSet)

urlpatterns = [
    # Landing page and user interface routes
    path('', views.landing_index, name='landing_index'),
    path('about/', views.about, name='about'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('dashboard/citizen/', views.citizen_dashboard, name='citizen_dashboard'),
    path('dashboard/authority/', views.authority_dashboard, name='authority_dashboard'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('reports/submit/', views.report_submit, name='report_submit'),
    path('reports/', views.report_list, name='report_list'),
    path('alerts/history/', views.alert_history, name='alert_history'),
    path('map/', views.map_view, name='map_view'),
    
    # API routes
    path('api/v1/dashboard/stats/', views.api_dashboard_stats, name='api-dashboard-stats'),
    path('api/v1/', include(router.urls)),
]