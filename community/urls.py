from django.urls import path
from . import views

app_name = 'community'

urlpatterns = [
    path('reports/', views.report_list, name='report_list'),
    path('reports/create/', views.create_report, name='create_report'),
    path('reports/<int:report_id>/', views.report_detail, name='report_detail'),
    path('reports/<int:report_id>/comment/', views.add_comment, name='add_comment'),
]
