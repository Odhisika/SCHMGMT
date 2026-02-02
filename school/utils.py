from django.shortcuts import get_object_or_404
from .models import School


def get_current_school(request):
    """
    Helper to get the current school from the request.
    It checks in order of priority:
    1. Subdomain from hostname
    2. Authenticated User's school
    3. Session variable 'school_slug' (for testing/superadmin switching)
    4. Default to the first school if exists (fallback)
    """
    # 1. Check subdomain from hostname (highest priority for SaaS)
    host = request.get_host().split(':')[0]  # Remove port if present
    if '.' in host and not host.startswith('www') and not host.startswith('localhost'):
        subdomain = host.split('.')[0]
        try:
            return School.objects.get(subdomain=subdomain)
        except School.DoesNotExist:
            pass
    
    # 2. If user is logged in and not superuser, their school is binding
    if request.user.is_authenticated and not request.user.is_superuser:
        if request.user.school:
            return request.user.school
            
    # 3. Check session (useful for superadmins or unauthenticated flows)
    school_slug = request.session.get('school_slug')
    if school_slug:
        try:
            return School.objects.get(slug=school_slug)
        except School.DoesNotExist:
            pass
            
    # 4. Fallback: Return the first school created (Default)
    # This ensures the app works immediately after migration if a school exists
    first_school = School.objects.first()
    if first_school:
        return first_school
        
    return None


def get_school_from_subdomain(host):
    """
    Extract school from subdomain
    """
    if '.' in host and not host.startswith('www') and not host.startswith('localhost'):
        subdomain = host.split('.')[0]
        try:
            return School.objects.get(subdomain=subdomain)
        except School.DoesNotExist:
            return None
    return None
