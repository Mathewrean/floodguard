from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='dashboard_home'),
    path('user/', views.user_dashboard, name='user_dashboard'),
    path('widgets/alerts/', views.alerts_widget, name='alerts_widget'),
    path('widgets/reports/', views.reports_widget, name='reports_widget'),
    path('widgets/weather/', views.weather_widget, name='weather_widget'),
    path('widgets/sensors/', views.sensors_widget, name='sensors_widget'),
    path('widgets/stats/', views.stats_widget, name='stats_widget'),
]
