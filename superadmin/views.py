from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.contrib.auth import get_user_model

from school.models import School
from .forms import SchoolCreationForm, SchoolAdminCreationForm

User = get_user_model()


def is_superuser(user):
    """Check if user is a superuser"""
    return user.is_authenticated and user.is_superuser


@login_required
@user_passes_test(is_superuser, login_url='/')
def dashboard(request):
    """Super admin dashboard"""
    schools = School.objects.all().order_by('-created_at')
    
    context = {
        'title': _('Super Admin Dashboard'),
        'schools': schools,
        'total_schools': schools.count(),
        'active_schools': schools.filter(is_active=True).count(),
        'total_users': User.objects.exclude(is_superuser=True).count(),
    }
    return render(request, 'superadmin/dashboard.html', context)


@login_required
@user_passes_test(is_superuser, login_url='/')
def school_list(request):
    """List all schools"""
    schools = School.objects.all().order_by('-created_at')
    
    context = {
        'title': _('Schools Management'),
        'schools': schools,
    }
    return render(request, 'superadmin/school_list.html', context)


@login_required
@user_passes_test(is_superuser, login_url='/')
def school_create(request):
    """Create a new school with admin"""
    if request.method == 'POST':
        school_form = SchoolCreationForm(request.POST, request.FILES)
        admin_form = SchoolAdminCreationForm(request.POST)
        
        if school_form.is_valid() and admin_form.is_valid():
            try:
                with transaction.atomic():
                    # Create school
                    school = school_form.save()
                    
                    # Create admin user
                    admin = admin_form.save(commit=False)
                    admin.school = school
                    admin.is_school_admin = True
                    admin.is_staff = True  # Allow access to Django admin
                    admin.save()
                    
                    messages.success(
                        request,
                        _(f'School "{school.name}" created successfully with admin "{admin.username}"')
                    )
                    return redirect('superadmin:school_detail', pk=school.pk)
            except Exception as e:
                messages.error(request, _(f'Error creating school: {str(e)}'))
        else:
            messages.error(request, _('Please correct the errors below.'))
    else:
        school_form = SchoolCreationForm()
        admin_form = SchoolAdminCreationForm()
    
    context = {
        'title': _('Create New School'),
        'school_form': school_form,
        'admin_form': admin_form,
    }
    return render(request, 'superadmin/school_form.html', context)


@login_required
@user_passes_test(is_superuser, login_url='/')
def school_detail(request, pk):
    """View school details"""
    school = get_object_or_404(School, pk=pk)
    
    admins = school.users.filter(is_school_admin=True)
    students = school.users.filter(is_student=True)
    teachers = school.users.filter(is_lecturer=True)
    
    context = {
        'title': _(f'School: {school.name}'),
        'school': school,
        'admins': admins,
        'students_count': students.count(),
        'teachers_count': teachers.count(),
        'total_users': school.users.count(),
    }
    return render(request, 'superadmin/school_detail.html', context)


@login_required
@user_passes_test(is_superuser, login_url='/')
def school_edit(request, pk):
    """Edit school details"""
    school = get_object_or_404(School, pk=pk)
    
    if request.method == 'POST':
        form = SchoolCreationForm(request.POST, request.FILES, instance=school)
        if form.is_valid():
            form.save()
            messages.success(request, _(f'School "{school.name}" updated successfully'))
            return redirect('superadmin:school_detail', pk=school.pk)
        messages.error(request, _('Please correct the errors below.'))
    else:
        form = SchoolCreationForm(instance=school)
    
    context = {
        'title': _(f'Edit School: {school.name}'),
        'school_form': form,
        'school': school,
        'is_edit': True,
    }
    return render(request, 'superadmin/school_form.html', context)


@login_required
@user_passes_test(is_superuser, login_url='/')
def school_toggle_active(request, pk):
    """Activate or deactivate a school"""
    school = get_object_or_404(School, pk=pk)
    
    if request.method == 'POST':
        school.is_active = not school.is_active
        school.save()
        
        status = _("activated") if school.is_active else _("deactivated")
        messages.success(request, _(f'School "{school.name}" has been {status}'))
        
    return redirect('superadmin:school_detail', pk=school.pk)


@login_required
@user_passes_test(is_superuser, login_url='/')
def school_add_admin(request, pk):
    """Add an admin to a school"""
    school = get_object_or_404(School, pk=pk)
    
    if request.method == 'POST':
        form = SchoolAdminCreationForm(request.POST)
        if form.is_valid():
            admin = form.save(commit=False)
            admin.school = school
            admin.is_school_admin = True
            admin.is_staff = True
            admin.save()
            
            messages.success(
                request,
                _(f'Admin "{admin.username}" added to "{school.name}"')
            )
            return redirect('superadmin:school_detail', pk=school.pk)
        messages.error(request, _('Please correct the errors below.'))
    else:
        form = SchoolAdminCreationForm()
    
    context = {
        'title': _(f'Add Admin to {school.name}'),
        'admin_form': form,
        'school': school,
    }
    return render(request, 'superadmin/school_add_admin.html', context)
