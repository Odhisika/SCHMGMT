from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from accounts.decorators import lecturer_required
from course.models import Course

from .forms import CourseFileForm, CourseVideoForm
from .models import CourseFile, CourseVideo


# ============================================================================
# Resources Overview
# ============================================================================

@login_required
def resources_overview(request):
    """Show all courses with their resource counts for quick access"""
    if request.user.is_student:
        # Students see only their enrolled courses
        from result.models import TakenCourse
        courses = Course.objects.filter(
            taken_courses__student__student=request.user,
            school=request.school
        ).distinct().annotate(
            file_count=Count('resource_files'),
            video_count=Count('resource_videos')
        ).order_by('-id')
    elif request.user.is_superuser or request.user.is_school_admin:
        # Admins see all courses in their school
        courses = Course.objects.filter(
            school=request.school
        ).annotate(
            file_count=Count('resource_files'),
            video_count=Count('resource_videos')
        ).order_by('-id')
    else:
        # Teachers see courses in their division OR courses they are assigned to
        teacher_query = Q(school=request.school)
        
        # Filter by division if set
        if hasattr(request.user, 'division') and request.user.division:
            teacher_query &= (Q(program__division=request.user.division) | Q(allocated_course__teacher=request.user))
        else:
            # If no division, only show allocated courses
            teacher_query &= Q(allocated_course__teacher=request.user)
            
        courses = Course.objects.filter(
            teacher_query
        ).distinct().annotate(
            file_count=Count('resource_files'),
            video_count=Count('resource_videos')
        ).order_by('-id')
    
    # Filter courses that have at least one resource
    courses_with_resources = courses.filter(Q(file_count__gt=0) | Q(video_count__gt=0))
    
    context = {
        'title': _('Learning Resources'),
        'courses': courses,
        'courses_with_resources': courses_with_resources,
        'total_files': sum(c.file_count for c in courses),
        'total_videos': sum(c.video_count for c in courses),
    }
    
    return render(request, 'resources/overview.html', context)


# ============================================================================
# Resource List View
# ============================================================================

@login_required
def resource_list(request, course_slug):
    """Display all resources (files and videos) for a course"""
    course = get_object_or_404(
        Course.objects.select_related('school', 'program'),
        slug=course_slug,
        school=request.school
    )
    
    # Check if user can access this course
    if request.user.is_student:
        # Students can only access courses they're enrolled in
        from result.models import TakenCourse
        if not TakenCourse.objects.filter(
            student__student=request.user,
            course=course
        ).exists():
            raise PermissionDenied(_("You are not enrolled in this course."))
    elif not (request.user.is_superuser or request.user.is_school_admin):
        # Teachers can only access courses in their division OR allocated to them
        teacher_query = Q(pk=course.pk)
        
        # Add filtering logic
        pass

    files = CourseFile.objects.filter(course=course).order_by('-updated_date')
    videos = CourseVideo.objects.filter(course=course).order_by('-updated_at')
    
    can_manage = request.user.is_superuser or request.user.is_school_admin or course.allocated_course.filter(teacher=request.user).exists()
    
    context = {
        'title': course.title,
        'course': course,
        'files': files,
        'videos': videos,
        'can_manage': can_manage,
    }
    
    return render(request, 'resources/resource_list.html', context)


def _check_resource_access(user, course):
    """Helper to check if a user can access a course resource"""
    if user.is_superuser or user.is_school_admin:
        return True
    
    if user.is_student:
        from result.models import TakenCourse
        return TakenCourse.objects.filter(student__student=user, course=course).exists()
    
    # Teachers can access their allocated courses or division courses
    if hasattr(user, 'division') and user.division and course.program.division == user.division:
        return True
        
    return course.allocated_course.filter(teacher=user).exists()


@login_required
def file_download(request, course_slug, file_id):
    """Serve a course file for download or in-browser viewing"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    
    if not _check_resource_access(request.user, course):
        raise PermissionDenied(_("You are not authorized to access this resource."))
        
    course_file = get_object_or_404(CourseFile, pk=file_id, course=course)
    
    # Increment download count
    course_file.downloads += 1
    course_file.save(update_fields=['downloads'])
    
    # Check if user wants to view in browser
    view_in_browser = request.GET.get('view') == 'true'
    
    # Serve the file
    response = FileResponse(
        course_file.file.open(),
        as_attachment=not view_in_browser
    )
    
    # Set filename if viewing in browser (some browsers need this)
    if view_in_browser:
        response['Content-Disposition'] = f'inline; filename="{course_file.file.name.split("/")[-1]}"'
        
    return response


@login_required
def video_detail(request, course_slug, video_slug):
    """Display video player and metadata"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    
    if not _check_resource_access(request.user, course):
        raise PermissionDenied(_("You are not authorized to access this resource."))
        
    video = get_object_or_404(CourseVideo, slug=video_slug, course=course)
    
    # Increment views
    video.increment_views()
    
    context = {
        'title': video.title,
        'course': course,
        'video': video,
        'can_manage': request.user.is_superuser or request.user.is_school_admin or course.allocated_course.filter(teacher=request.user).exists()
    }
    
    return render(request, 'resources/video_detail.html', context)


@login_required
@lecturer_required
def file_edit(request, course_slug, file_id):
    """Edit an existing course file"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    course_file = get_object_or_404(CourseFile, pk=file_id, course=course)
    
    # Check permission (Admins or the uploader can edit)
    if not (request.user.is_superuser or request.user.is_school_admin or course_file.uploaded_by == request.user):
        messages.error(request, _("You don't have permission to edit this file."))
        return redirect('resources:resource_list', course_slug=course_slug)
        
    if request.method == "POST":
        form = CourseFileForm(request.POST, request.FILES, instance=course_file)
        if form.is_valid():
            form.save()
            messages.success(request, _("File updated successfully."))
            return redirect('resources:resource_list', course_slug=course_slug)
    else:
        form = CourseFileForm(instance=course_file)
        
    context = {
        'title': _('Edit File'),
        'course': course,
        'file_obj': course_file,
        'form': form,
    }
    return render(request, 'resources/upload_file.html', context)


@login_required
@lecturer_required
@require_http_methods(["POST"])
def file_delete(request, course_slug, file_id):
    """Delete a course file"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    course_file = get_object_or_404(CourseFile, pk=file_id, course=course)
    
    # Check permission (Admins or the uploader can delete)
    if not (request.user.is_superuser or request.user.is_school_admin or course_file.uploaded_by == request.user):
        messages.error(request, _("You don't have permission to delete this file."))
    else:
        course_file.delete()
        messages.success(request, _("File deleted successfully."))
        
    return redirect('resources:resource_list', course_slug=course_slug)


@login_required
@lecturer_required
def video_edit(request, course_slug, video_slug):
    """Edit an existing course video"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    video = get_object_or_404(CourseVideo, slug=video_slug, course=course)
    
    # Check permission
    if not (request.user.is_superuser or request.user.is_school_admin or video.uploaded_by == request.user):
        messages.error(request, _("You don't have permission to edit this video."))
        return redirect('resources:resource_list', course_slug=course_slug)
        
    if request.method == "POST":
        form = CourseVideoForm(request.POST, request.FILES, instance=video)
        if form.is_valid():
            form.save()
            messages.success(request, _("Video updated successfully."))
            return redirect('resources:resource_list', course_slug=course_slug)
    else:
        form = CourseVideoForm(instance=video)
        
    context = {
        'title': _('Edit Video'),
        'course': course,
        'video': video,
        'form': form,
    }
    return render(request, 'resources/upload_video.html', context)


@login_required
@lecturer_required
@require_http_methods(["POST"])
def video_delete(request, course_slug, video_slug):
    """Delete a course video"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    video = get_object_or_404(CourseVideo, slug=video_slug, course=course)
    
    # Check permission
    if not (request.user.is_superuser or request.user.is_school_admin or video.uploaded_by == request.user):
        messages.error(request, _("You don't have permission to delete this video."))
    else:
        video.delete()
        messages.success(request, _("Video deleted successfully."))
        
    return redirect('resources:resource_list', course_slug=course_slug)


@login_required
@lecturer_required
def file_upload(request, course_slug):
    """Upload a new file to a course"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    
    # Check if user can manage this course
    can_manage = request.user.is_superuser or request.user.is_school_admin or course.allocated_course.filter(teacher=request.user).exists()
    if not can_manage:
        messages.error(request, _("You are not authorized to upload resources to this course."))
        return redirect('resources:resource_list', course_slug=course_slug)
        
    if request.method == "POST":
        form = CourseFileForm(request.POST, request.FILES)
        if form.is_valid():
            course_file = form.save(commit=False)
            course_file.course = course
            course_file.school = request.school
            course_file.uploaded_by = request.user
            course_file.save()
            messages.success(request, _("File uploaded successfully."))
            return redirect('resources:resource_list', course_slug=course_slug)
    else:
        form = CourseFileForm()
        
    context = {
        'title': _('Upload File'),
        'course': course,
        'form': form,
    }
    return render(request, 'resources/upload_file.html', context)


@login_required
@lecturer_required
def video_upload(request, course_slug):
    """Upload a new video to a course"""
    course = get_object_or_404(Course, slug=course_slug, school=request.school)
    
    # Check if user can manage this course
    can_manage = request.user.is_superuser or request.user.is_school_admin or course.allocated_course.filter(teacher=request.user).exists()
    if not can_manage:
        messages.error(request, _("You are not authorized to upload resources to this course."))
        return redirect('resources:resource_list', course_slug=course_slug)
        
    if request.method == "POST":
        form = CourseVideoForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.course = course
            video.school = request.school
            video.uploaded_by = request.user
            video.save()
            messages.success(request, _("Video uploaded successfully."))
            return redirect('resources:resource_list', course_slug=course_slug)
    else:
        form = CourseVideoForm()
        
    context = {
        'title': _('Upload Video'),
        'course': course,
        'form': form,
    }
    return render(request, 'resources/upload_video.html', context)
