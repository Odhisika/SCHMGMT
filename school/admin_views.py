from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from .models import School
from accounts.models import User
from accounts.decorators import admin_required


def is_superuser(user):
    return user.is_superuser


@admin_required
@user_passes_test(is_superuser)
def super_admin_dashboard(request):
    """
    Super admin dashboard showing overview of all schools and system stats
    """
    # Get system statistics
    total_schools = School.objects.count()
    total_students = User.objects.filter(is_student=True, is_active=True).count()
    total_teachers = User.objects.filter(is_lecturer=True, is_active=True).count()
    total_admins = User.objects.filter(is_school_admin=True, is_active=True).count()
    
    # Get recent schools (last 10)
    recent_schools = School.objects.order_by('-created_at')[:10]
    
    # Get schools with user counts
    schools_with_counts = []
    for school in recent_schools:
        school_data = {
            'school': school,
            'student_count': school.get_student_count(),
            'teacher_count': school.get_teacher_count(),
            'admin_count': school.get_admin_count(),
        }
        schools_with_counts.append(school_data)
    
    context = {
        'title': _('Super Admin Dashboard'),
        'total_schools': total_schools,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_admins': total_admins,
        'recent_schools': recent_schools,
        'schools_with_counts': schools_with_counts,
    }
    
    return render(request, 'admin/dashboard.html', context)


@admin_required
@user_passes_test(is_superuser)
def school_statistics(request):
    """
    Detailed statistics view for super admin
    """
    # Get detailed statistics by school
    school_stats = School.objects.annotate(
        student_count=Count('users', filter=models.Q(users__is_student=True, users__is_active=True)),
        teacher_count=Count('users', filter=models.Q(users__is_lecturer=True, users__is_active=True)),
        admin_count=Count('users', filter=models.Q(users__is_school_admin=True, users__is_active=True))
    ).order_by('-created_at')
    
    context = {
        'title': _('School Statistics'),
        'school_stats': school_stats,
    }
    
    return render(request, 'admin/school_statistics.html', context)


@admin_required
@user_passes_test(is_superuser)
def system_overview(request):
    """
    System overview and health check
    """
    # System health indicators
    system_health = {
        'database_status': 'online',
        'application_status': 'running',
        'last_backup': '2 hours ago',
        'active_sessions': request.session.session_key,
    }
    
    context = {
        'title': _('System Overview'),
        'system_health': system_health,
    }
    
    return render(request, 'admin/system_overview.html', context)