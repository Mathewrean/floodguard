from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
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
    path('safe-route/', views.safe_route_page, name='safe_route'),
    path('health/', views.health_view, name='health'),
    path('favicon.ico', views.favicon_view, name='favicon'),
    path('service-worker.js', views.service_worker_view, name='service-worker'),
    
    # API routes (versioned)
    path('api-token-auth/', obtain_auth_token, name='api_token_auth'),
    path('api/v1/stats/', views.stats_view, name='stats'),
    path('api/v1/data-sources/', views.data_sources_view, name='data-sources'),
    path('api/v1/ai-analysis/', views.ai_flood_analysis, name='ai-analysis'),
    path('api/v1/safe-route/', views.safe_route_view, name='safe-route'),
    path('api/v1/safe-route/snap/', views.snap_coordinate_view, name='safe-route-snap'),
    path('api/v1/dynamic-zone/', views.dynamic_zone_check, name='dynamic-zone'),
    path('api/v1/dashboard/stats/', views.api_dashboard_stats, name='api-dashboard-stats'),
    path('api/v1/global-search/', views.api_global_search, name='api-global-search'),
    path('api/v1/nearby-zones/', views.api_nearby_zones, name='api-nearby-zones'),
    path('api/v1/', include(router.urls)),
]
