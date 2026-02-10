from django.urls import path
from . import views
from . import lesson_note_views as ln_views


urlpatterns = [
    # Program urls
    path("", views.ProgramFilterView.as_view(), name="programs"),
    path("<int:pk>/detail/", views.program_detail, name="program_detail"),
    path("add/", views.program_add, name="add_program"),
    path("<int:pk>/edit/", views.program_edit, name="edit_program"),
    path("<int:pk>/delete/", views.program_delete, name="program_delete"),
    # Course urls
    path("course/<slug>/detail/", views.course_single, name="course_detail"),
    path("<int:pk>/course/add/", views.course_add, name="course_add"),
    path("course/<slug>/edit/", views.course_edit, name="edit_course"),
    path("course/delete/<slug>/", views.course_delete, name="delete_course"),
    # CourseAllocation urls
    path(
        "course/assign/",
        views.CourseAllocationFormView.as_view(),
        name="course_allocation",
    ),
    path(
        "course/allocated/",
        views.CourseAllocationFilterView.as_view(),
        name="course_allocation_view",
    ),
    path(
        "allocated_course/<int:pk>/edit/",
        views.edit_allocated_course,
        name="edit_allocated_course",
    ),
    path(
        "course/<int:pk>/deallocate/", views.deallocate_course, name="course_deallocate"
    ),
    # File uploads urls
    path(
        "course/<slug>/documentations/upload/",
        views.handle_file_upload,
        name="upload_file_view",
    ),
    path(
        "course/<slug>/documentations/<int:file_id>/edit/",
        views.handle_file_edit,
        name="upload_file_edit",
    ),
    path(
        "course/<slug>/documentations/<int:file_id>/delete/",
        views.handle_file_delete,
        name="upload_file_delete",
    ),
    # ############# UPLOAD video views #####################################
    path(
        "course/<slug:slug>/upload/video/", views.handle_video_upload, name="upload_video"
    ),
    path(
        "course/<slug:slug>/upload/video/<slug:video_slug>/",
        views.handle_video_single,
        name="video_single",
    ),
    path(
        "course/<slug:slug>/upload/video/<slug:video_slug>/edit/",
        views.handle_video_edit,
        name="video_edit",
    ),
    path(
        "course/<slug:slug>/upload/video/<slug:video_slug>/delete/",
        views.handle_video_delete,
        name="video_delete",
    ),
    # Lesson Note views
    path("lesson-notes/", ln_views.lesson_note_list, name="lesson_note_list"),
    path("lesson-notes/create/", ln_views.lesson_note_create, name="lesson_note_create"),
    path("lesson-notes/<int:pk>/", ln_views.lesson_note_detail, name="lesson_note_detail"),
    path("lesson-notes/<int:pk>/edit/", ln_views.lesson_note_edit, name="lesson_note_edit"),
    path("lesson-notes/<int:pk>/submit/", ln_views.lesson_note_submit, name="lesson_note_submit"),
    path("lesson-notes/<int:pk>/delete/", ln_views.lesson_note_delete, name="lesson_note_delete"),
    # Admin lesson note views
    path("admin/lesson-notes/", ln_views.lesson_note_admin_list, name="lesson_note_admin_list"),
    path("admin/lesson-notes/<int:pk>/review/", ln_views.lesson_note_admin_review, name="lesson_note_admin_review"),
    # course registration
    path("course/registration/", views.course_registration, name="course_registration"),
    path("course/drop/", views.course_drop, name="course_drop"),
    path("my_courses/", views.user_course_list, name="user_course_list"),
]
