from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


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
        messages.error(request, "Access denied. School administrator required.")
        return redirect(redirect_to)

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
        messages.error(request, "Access denied. Lecturer or school admin required.")
        return redirect(redirect_to)

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
            messages.error(request, "Access denied. School admin required.")
            return redirect(redirect_to)
        
        # For school admins, ensure they're accessing their own school's data
        if (hasattr(request, 'school') and 
            request.user.is_school_admin and 
            not request.user.is_superuser and
            request.school != request.user.school):
            messages.error(request, "Access denied to other school's data.")
            return redirect(redirect_to)
            
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
            messages.error(request, "Access denied. School staff required.")
            return redirect(redirect_to)
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
            messages.error(request, "Access denied. School management permissions required.")
            return redirect(redirect_to)
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
        messages.error(request, "Access denied. Student or school admin required.")
        return redirect(redirect_to)

    return wrapper if function else test_func
