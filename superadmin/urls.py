from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # School Management
    path('schools/', views.school_list, name='school_list'),
    path('schools/create/', views.school_create, name='school_create'),
    path('schools/<int:pk>/', views.school_detail, name='school_detail'),
    path('schools/<int:pk>/edit/', views.school_edit, name='school_edit'),
    path('schools/<int:pk>/toggle-active/', views.school_toggle_active, name='school_toggle_active'),
    path('schools/<int:pk>/add-admin/', views.school_add_admin, name='school_add_admin'),
    path('schools/<int:pk>/reset-password/', views.school_reset_admin_password, name='school_reset_admin_password'),
    path('schools/<int:pk>/delete/', views.school_delete, name='school_delete'),
]
