from django.conf import settings


def school_context(request):
    """
    Add school information to template context for tenant-aware branding
    """
    context = {}
    
    if hasattr(request, 'school') and request.school:
        context['current_school'] = request.school
        context['school_branding'] = {
            'name': request.school.name,
            'primary_color': request.school.primary_color,
            'secondary_color': request.school.secondary_color,
            'logo_url': request.school.logo.url if request.school.logo else None,
            'subdomain': request.school.subdomain,
        }
        
        # Add school-specific navigation items
        context['school_nav_items'] = [
            {'name': 'Dashboard', 'url': 'dashboard', 'icon': 'tachometer-alt'},
            {'name': 'Students', 'url': 'student_list', 'icon': 'user-graduate'},
            {'name': 'Teachers', 'url': 'lecturer_list', 'icon': 'chalkboard-teacher'},
            {'name': 'Courses', 'url': 'programs', 'icon': 'book'},
            {'name': 'Timetable', 'url': 'timetable_dashboard', 'icon': 'table'},
        ]
    
    # Add global context
    context['site_name'] = getattr(settings, 'SITE_NAME', 'SkyLearn')
    context['site_description'] = getattr(settings, 'SITE_DESCRIPTION', 'School Management System')
    
    return context


def tenant_aware_urls(request):
    """
    Provide tenant-aware URLs for templates
    """
    context = {}
    
    if hasattr(request, 'school') and request.school:
        school_slug = request.school.subdomain
        context.update({
            'school_dashboard_url': f'/{request.LANGUAGE_CODE}/dashboard/',
            'school_students_url': f'/{request.LANGUAGE_CODE}/students/',
            'school_teachers_url': f'/{request.LANGUAGE_CODE}/teachers/',
            'school_courses_url': f'/{request.LANGUAGE_CODE}/programs/',
        })
    
    return context