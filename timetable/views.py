from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from accounts.decorators import admin_required
from .models import Period, TimetableEntry
from .forms import PeriodForm, TimetableEntryForm
from core.models import Term
from django.conf import settings


# ========== Period Management Views ==========

@login_required
@admin_required
def period_list(request):
    """List all periods for the school"""
    periods = Period.objects.filter(school=request.school).order_by('order')
    context = {
        'title': _('Period Management'),
        'periods': periods,
    }
    return render(request, 'timetable/period_list.html', context)


@login_required
@admin_required
def period_add(request):
    """Add a new period"""
    if request.method == 'POST':
        form = PeriodForm(request.POST)
        if form.is_valid():
            period = form.save(commit=False)
            period.school = request.school
            period.save()
            messages.success(request, _('Period created successfully!'))
            return redirect('timetable:period_list')
        messages.error(request, _('Please correct the errors below.'))
    else:
        form = PeriodForm()
    
    context = {
        'title': _('Add Period'),
        'form': form,
    }
    return render(request, 'timetable/period_form.html', context)


@login_required
@admin_required
def period_edit(request, pk):
    """Edit an existing period"""
    period = get_object_or_404(Period, pk=pk, school=request.school)
    
    if request.method == 'POST':
        form = PeriodForm(request.POST, instance=period)
        if form.is_valid():
            form.save()
            messages.success(request, _('Period updated successfully!'))
            return redirect('timetable:period_list')
        messages.error(request, _('Please correct the errors below.'))
    else:
        form = PeriodForm(instance=period)
    
    context = {
        'title': _('Edit Period'),
        'form': form,
        'period': period,
    }
    return render(request, 'timetable/period_form.html', context)


@login_required
@admin_required
def period_delete(request, pk):
    """Delete a period"""
    period = get_object_or_404(Period, pk=pk, school=request.school)
    
    if request.method == 'POST':
        period.delete()
        messages.success(request, _('Period deleted successfully!'))
        return redirect('timetable:period_list')
    
    context = {
        'title': _('Delete Period'),
        'period': period,
    }
    return render(request, 'timetable/period_confirm_delete.html', context)


# ========== Timetable Views ==========

@login_required
def timetable_dashboard(request):
    """Main timetable dashboard - with role-based filtering"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    
    # Determine accessible levels
    if request.user.is_superuser or request.user.is_school_admin:
        levels = settings.LEVEL_CHOICES
    elif request.user.is_student:
        # Students see only their own level
        student = Student.objects.get(student=request.user)
        # Find the display name for the student's level
        level_name = dict(settings.LEVEL_CHOICES).get(student.level, student.level)
        levels = [(student.level, level_name)]
    elif request.user.is_teacher or request.user.is_lecturer:
        # Teachers see only levels in their division
        from accounts.utils import filter_levels_by_division
        levels = filter_levels_by_division(request.user)
    else:
        levels = []

    # Organize levels by division/section for display
    # We can try to group them: Nursery, Primary, JHS
    # Or just pass the list and let template iterate. 
    # Given the template was hardcoded, passing a structured dict might be better.
    
    from accounts.utils import get_division_for_level
    
    grouped_levels = {}
    for code, name in levels:
        division = get_division_for_level(code)
        if not division:
            division = "Other"
        
        if division not in grouped_levels:
            grouped_levels[division] = []
        grouped_levels[division].append((code, name))
        
    # Sort order for divisions
    division_order = [settings.DIVISION_NURSERY, settings.DIVISION_PRIMARY, settings.DIVISION_JHS, "Other"]
    sorted_grouped_levels = []
    for div in division_order:
        if div in grouped_levels:
            sorted_grouped_levels.append((dict(settings.DIVISION_CHOICES).get(div, div), grouped_levels[div]))

    context = {
        'title': _('Timetable Dashboard'),
        'current_term': current_term,
        'grouped_levels': sorted_grouped_levels,
    }
    return render(request, 'timetable/dashboard.html', context)


@login_required
def timetable_by_class(request, level):
    """View timetable for a specific class/level - with strict access control"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    
    if not current_term:
        messages.error(request, _('No active term found.'))
        return redirect('timetable:timetable_dashboard')

    # ACCESS CONTROL CHECK
    has_access = False
    if request.user.is_superuser or request.user.is_school_admin:
        has_access = True
    elif request.user.is_student:
        # Student can only access their own level
        try:
            student = Student.objects.get(student=request.user)
            if student.level == level:
                has_access = True
        except Student.DoesNotExist:
            pass
    elif request.user.is_teacher or request.user.is_lecturer:
        # Teacher can only access levels in their division
        from accounts.utils import check_teacher_division_access
        if check_teacher_division_access(request.user, level):
            has_access = True
    
    if not has_access:
        messages.error(request, _("You do not have permission to view this timetable."))
        return redirect('timetable:timetable_dashboard')
    
    # Get all periods for this school (lesson periods only for the grid)
    lesson_periods = Period.objects.filter(
        school=request.school,
        period_type='LESSON'
    ).order_by('order')
    
    # Get all periods including breaks for reference
    all_periods = Period.objects.filter(school=request.school).order_by('order')
    
    # Get timetable entries for this class
    entries = TimetableEntry.objects.filter(
        school=request.school,
        term=current_term,
        level=level
    ).select_related('period', 'subject', 'teacher')
    
    # Organize entries by day and period
    days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY']
    timetable_grid = {}
    
    for day in days:
        timetable_grid[day] = {}
        day_entries = entries.filter(day_of_week=day)
        for entry in day_entries:
            timetable_grid[day][entry.period.id] = entry
    
    context = {
        'title': f'{dict(TimetableEntry.DAYS_OF_WEEK).get(level, level)} Timetable',
        'level': level,
        'level_display': dict(settings.LEVEL_CHOICES).get(level, level),
        'current_term': current_term,
        'lesson_periods': lesson_periods,
        'all_periods': all_periods,
        'days': days,
        'timetable_grid': timetable_grid,
        'DAYS_DISPLAY': dict(TimetableEntry.DAYS_OF_WEEK),
    }
    return render(request, 'timetable/timetable_by_class.html', context)


@login_required
@admin_required
def timetable_entry_add(request):
    """Add a new timetable entry"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    if not current_term:
        messages.error(request, _('No active term found.'))
        return redirect('timetable:timetable_dashboard')

    if request.method == 'POST':
        form = TimetableEntryForm(request.POST, school=request.school)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.school = request.school
            entry.term = current_term
            entry.save()
            messages.success(request, _('Entry added successfully!'))
            # Redirect back to the class view if possible
            return redirect('timetable:timetable_by_class', level=entry.level)
        messages.error(request, _('Please correct the errors below.'))
    else:
        # Pre-fill data if passed in GET params
        initial = {
            'level': request.GET.get('level'),
            'day_of_week': request.GET.get('day'),
            'period': request.GET.get('period'),
        }
        form = TimetableEntryForm(school=request.school, initial=initial)
    
    context = {
        'title': _('Add Timetable Entry'),
        'form': form,
    }
    return render(request, 'timetable/entry_form.html', context)


@login_required
@admin_required
def timetable_entry_edit(request, pk):
    """Edit a timetable entry"""
    entry = get_object_or_404(TimetableEntry, pk=pk, school=request.school)
    
    if request.method == 'POST':
        form = TimetableEntryForm(request.POST, instance=entry, school=request.school)
        if form.is_valid():
            form.save()
            messages.success(request, _('Entry updated successfully!'))
            return redirect('timetable:timetable_by_class', level=entry.level)
        messages.error(request, _('Please correct the errors below.'))
    else:
        form = TimetableEntryForm(instance=entry, school=request.school)
    
    context = {
        'title': _('Edit Timetable Entry'),
        'form': form,
    }
    return render(request, 'timetable/entry_form.html', context)


@login_required
@admin_required
def timetable_entry_delete(request, pk):
    """Delete a timetable entry"""
    entry = get_object_or_404(TimetableEntry, pk=pk, school=request.school)
    level_redirect = entry.level
    
    if request.method == 'POST':
        entry.delete()
        messages.success(request, _('Entry deleted successfully!'))
        return redirect('timetable:timetable_by_class', level=level_redirect)
    
    context = {
        'title': _('Delete Entry'),
        'entry': entry,
    }
    return render(request, 'timetable/entry_confirm_delete.html', context)


@login_required
@admin_required
def timetable_generate(request):
    """Auto-generate timetable logic"""
    if request.method == 'POST':
        # Logic to call the auto-generation function
        # For now, just a placeholder or basic implementation
        from .utils import auto_generate_timetable
        
        current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
        if not current_term:
            messages.error(request, _('No active term found.'))
            return redirect('timetable:timetable_dashboard')
            
        success, message = auto_generate_timetable(request.school, current_term)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
            
        return redirect('timetable:timetable_dashboard')
        
    return render(request, 'timetable/generate_confirm.html', {'title': _('Generate Timetable')})
