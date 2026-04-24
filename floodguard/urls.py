from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # API endpoints
    path('api/alerts/', include('alerts.urls')),
    path('api/community/', include('community.urls')),
    path('api/dashboard/', include('dashboard.urls')),
    path('api/data_ingestion/', include('data_ingestion.urls')),

    # Main dashboard at root
    path('', include('dashboard.urls', namespace='main')),
]
