from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


def _deny(request, message, redirect_to):
    """Add one denial notice and redirect without looping back to itself.

    Permission decorators historically pointed at ``/dashboard/``, which is
    itself admin-only. A denied teacher/student would bounce between the
    protected page and the dashboard, stacking "Access denied" messages on
    every hop. If the redirect target is the page already being requested we
    fall back to the public home page instead. The comparison ignores the
    active language prefix (for example ``/en/dashboard/``).
    """
    messages.error(request, message)
    if request.path.rstrip("/").endswith(redirect_to.rstrip("/")):
        redirect_to = "/"
    return redirect(redirect_to)


def admin_required(
    function=None,
    redirect_to="/dashboard/",
):
    """
    Decorator for views that checks that the logged-in user is a superuser OR school admin,
    redirects to the specified URL if necessary.
    """

    # Define the test function: checks if the user is active and a superuser or school admin
    def test_func(user):
        return user.is_active and (user.is_superuser or user.is_school_admin)

    # Define the wrapper function to handle the response
    def wrapper(request, *args, **kwargs):
        if test_func(request.user):
            # Call the original function if the user passes the test
            return function(request, *args, **kwargs) if function else None
        # Redirect to the specified URL if the user fails the test
        return _deny(
            request,
            "Access denied. School administrator required.",
            redirect_to,
        )

    return wrapper if function else test_func


def lecturer_required(
    function=None,
    redirect_to="/dashboard/",
):
    """
    Decorator for views that checks that the logged-in user is a lecturer,
    school admin, or superuser, redirects to the specified URL if necessary.
    """

    # Define the test function: checks if the user is active and a lecturer, teacher, school admin, or superuser
    def test_func(user):
        return user.is_active and (user.is_lecturer or user.is_teacher or user.is_school_admin or user.is_superuser)

    # Define the wrapper function to handle the response
    def wrapper(request, *args, **kwargs):
        if test_func(request.user):
            # Call the original function if the user passes the test
            return function(request, *args, **kwargs) if function else None
        # Redirect to the specified URL if the user fails the test
        return _deny(
            request,
            "Access denied. Lecturer or school admin required.",
            redirect_to,
        )

    return wrapper if function else test_func


def school_admin_required(function=None, redirect_to="/dashboard/"):
    """
    Decorator for views that checks that the logged-in user is a school admin
    or superuser, and ensures they're accessing their own school's data.
    """
    def test_func(user):
        return user.is_active and (user.is_school_admin or user.is_superuser)
    
    def wrapper(request, *args, **kwargs):
        if not test_func(request.user):
            return _deny(
                request,
                "Access denied. School admin required.",
                redirect_to,
            )
        
        # For school admins, ensure they're accessing their own school's data
        if (hasattr(request, 'school') and 
            request.user.is_school_admin and 
            not request.user.is_superuser and
            request.school != request.user.school):
            return _deny(
                request,
                "Access denied to other school's data.",
                redirect_to,
            )
            
        return function(request, *args, **kwargs) if function else None
    
    return wrapper if function else test_func


def school_staff_required(function=None, redirect_to="/dashboard/"):
    """
    Decorator for views that checks that the logged-in user is school staff
    (school admin, lecturer, department head, or class teacher) or superuser.
    """
    def test_func(user):
        return user.is_active and (user.is_school_staff or user.is_superuser)
    
    def wrapper(request, *args, **kwargs):
        if not test_func(request.user):
            return _deny(
                request,
                "Access denied. School staff required.",
                redirect_to,
            )
        return function(request, *args, **kwargs) if function else None
    
    return wrapper if function else test_func


def can_manage_school_required(function=None, redirect_to="/dashboard/"):
    """
    Decorator for views that checks that the user can manage school settings
    (superuser or school admin).
    """
    def test_func(user):
        return user.is_active and user.can_manage_school
    
    def wrapper(request, *args, **kwargs):
        if not test_func(request.user):
            return _deny(
                request,
                "Access denied. School management permissions required.",
                redirect_to,
            )
        return function(request, *args, **kwargs) if function else None
    
    return wrapper if function else test_func


def student_required(
    function=None,
    redirect_to="/dashboard/",
):
    """
    Decorator for views that checks that the logged-in user is a student,
    school admin, or superuser, redirects to the specified URL if necessary.
    """

    # Define the test function: checks if the user is active and a student, school admin or superuser
    def test_func(user):
        return user.is_active and (user.is_student or user.is_school_admin or user.is_superuser)

    # Define the wrapper function to handle the response
    def wrapper(request, *args, **kwargs):
        if test_func(request.user):
            # Call the original function if the user passes the test
            return function(request, *args, **kwargs) if function else None
        # Redirect to the specified URL if the user fails the test
        return _deny(
            request,
            "Access denied. Student or school admin required.",
            redirect_to,
        )

    return wrapper if function else test_func
