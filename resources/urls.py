from django.urls import path
from . import views

app_name = 'resources'

urlpatterns = [
    # Overview
    path('', views.resources_overview, name='overview'),
    
    # Resource list
    path('course/<slug:course_slug>/', views.resource_list, name='resource_list'),
    
    # File management
    path('course/<slug:course_slug>/files/upload/', views.file_upload, name='file_upload'),
    path('course/<slug:course_slug>/files/<int:file_id>/edit/', views.file_edit, name='file_edit'),
    path('course/<slug:course_slug>/files/<int:file_id>/delete/', views.file_delete, name='file_delete'),
    path('course/<slug:course_slug>/files/<int:file_id>/download/', views.file_download, name='file_download'),
    
    # Video management
    path('course/<slug:course_slug>/videos/upload/', views.video_upload, name='video_upload'),
    path('course/<slug:course_slug>/videos/<slug:video_slug>/', views.video_detail, name='video_detail'),
    path('course/<slug:course_slug>/videos/<slug:video_slug>/edit/', views.video_edit, name='video_edit'),
    path('course/<slug:course_slug>/videos/<slug:video_slug>/delete/', views.video_delete, name='video_delete'),
]
