from django.urls import path
from .admin_views import (
    super_admin_dashboard,
    school_statistics,
    system_overview
)

app_name = 'admin'

urlpatterns = [
    path('', super_admin_dashboard, name='super_admin_dashboard'),
    path('statistics/', school_statistics, name='school_statistics'),
    path('system/', system_overview, name='system_overview'),
]