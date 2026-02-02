from django.urls import path
from . import views

app_name = 'timetable'

urlpatterns = [
    # Period Management
    path('periods/', views.period_list, name='period_list'),
    path('periods/add/', views.period_add, name='period_add'),
    path('periods/<int:pk>/edit/', views.period_edit, name='period_edit'),
    path('periods/<int:pk>/delete/', views.period_delete, name='period_delete'),
    
    # Timetable Views
    path('', views.timetable_dashboard, name='timetable_dashboard'),
    path('class/<str:level>/', views.timetable_by_class, name='timetable_by_class'),
    
    # Entry Management
    path('entry/add/', views.timetable_entry_add, name='timetable_entry_add'),
    path('entry/<int:pk>/edit/', views.timetable_entry_edit, name='timetable_entry_edit'),
    path('entry/<int:pk>/delete/', views.timetable_entry_delete, name='timetable_entry_delete'),
    
    # Auto-generate
    path('generate/', views.timetable_generate, name='timetable_generate'),
]
