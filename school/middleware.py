from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from .utils import get_current_school


class SchoolMiddleware(MiddlewareMixin):
    """
    Middleware to enforce multi-tenancy and data isolation.
    
    Features:
    - Attaches current school to request
    - Enforces school isolation (users can only access their school's data)
    - Allows superusers to bypass restrictions
    - Handles subdomain-based routing
    """
    
    def process_request(self, request):
        """Attach the current school to the request object."""
        
        # Get current school from various sources (subdomain, user, session)
        school = get_current_school(request)
        request.school = school
        
        # Special handling for superadmin routes - no school required
        if request.path.startswith('/superadmin/') or request.path.startswith('/admin/'):
            return None
        
        # Allow access to static/media files
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return None
        
        # Superusers can access any school's data
        if request.user.is_authenticated and request.user.is_superuser:
            return None
        
        # For authenticated non-superusers, enforce school match
        if request.user.is_authenticated and not request.user.is_superuser:
            user_school = request.user.school
            
            # If user has no school, they shouldn't access the main app
            if not user_school:
                messages.error(request, _('Your account is not associated with any school. Please contact support.'))
                return redirect('login')
            
            # If the detected school doesn't match user's school, force redirect
            if school and school != user_school:
                messages.warning(request, _('Access denied. You can only access your own school.'))
                # Redirect to their school's subdomain or set session
                request.session['school_slug'] = user_school.slug
                return redirect(request.path)
            
            # Set school to user's school if not detected
            if not school:
                request.school = user_school
        
        # For unauthenticated users accessing protected routes
        if not request.user.is_authenticated:
            # Allow access to login, logout, public pages
            public_paths = ['/accounts/login/', '/accounts/logout/', '/accounts/signup/', '/']
            if not any(request.path.startswith(path) for path in public_paths):
                # If no school detected, redirect to login
                if not school:
                    return redirect('login')
        
        return None
    
    def process_template_response(self, request, response):
        """Add school context to all templates"""
        if hasattr(request, 'school') and request.school:
            if hasattr(response, 'context_data') and response.context_data is not None:
                response.context_data['current_school'] = request.school
        return response