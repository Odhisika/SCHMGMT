from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('', views.attendance_dashboard, name='dashboard'),
    path('mark/<str:level>/', views.mark_attendance, name='mark_attendance'),
    path('reports/', views.attendance_reports, name='reports'),
    path('my-attendance/', views.student_attendance_view, name='student_view'),
]
