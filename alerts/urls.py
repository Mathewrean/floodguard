from django.urls import path
from . import views

app_name = 'alerts'

urlpatterns = [
    path('', views.alert_list, name='alert_list'),
    path('create/', views.create_alert, name='create_alert'),
    path('<int:alert_id>/', views.alert_detail, name='alert_detail'),
]
