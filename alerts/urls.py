# alerts/urls.py
from django.urls import path
from . import views
from .views import health_check, alerts_api, AlertListView, AlertDetailView

app_name = 'alerts'

urlpatterns = [
    # API endpoints
    path('health/', health_check),
    path('api/dashboard/widgets/alerts/', alerts_api, name='alerts_api'),

    # DRF views for list/detail
    path('', AlertListView.as_view(), name='alert-list'),        # /api/alerts/
    path('<int:pk>/', AlertDetailView.as_view(), name='alert-detail'),  # /api/alerts/1/
]
