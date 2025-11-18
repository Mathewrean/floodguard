from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='dashboard_home'),
    path('alerts/', views.alerts_page, name='alerts_page'),
    path('reports/', views.reports_page, name='reports_page'),
    path('statistics/', views.statistics_page, name='statistics_page'),
    path('weather/', views.weather_page, name='weather_page'),
    path('sensors/', views.sensors_page, name='sensors_page'),
    path('admin-panel/', views.admin_panel_page, name='admin_panel_page'),
    path('user/', views.user_dashboard, name='user_dashboard'),
    path('widgets/alerts/', views.alerts_widget, name='alerts_widget'),
    path('widgets/reports/', views.reports_widget, name='reports_widget'),
    path('widgets/weather/', views.weather_widget, name='weather_widget'),
    path('widgets/sensors/', views.sensors_widget, name='sensors_widget'),
    path('widgets/stats/', views.stats_widget, name='stats_widget'),
    path('widgets/satellite/', views.satellite_widget, name='satellite_widget'),
]
