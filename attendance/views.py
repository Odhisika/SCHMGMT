from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils.dateparse import parse_date
from datetime import date, timedelta
from decimal import Decimal
from django.http import JsonResponse
from django.db.models import Sum
from django.utils import timezone

from accounts.decorators import lecturer_required, student_required, admin_required
from accounts.models import Student, Parent
from core.models import Term
from .models import Attendance, AttendanceSession, AttendanceSummary, PRESENT, ABSENT

@login_required
@lecturer_required
def attendance_dashboard(request):
    """Attendance overview for teachers/admins - filtered by division"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    today = date.today()
    
    # Filter levels by teacher's division
    if request.user.is_superuser or request.user.is_school_admin:
        accessible_levels = settings.LEVEL_CHOICES
    elif request.user.division:
        division_levels = request.user.get_division_levels()
        accessible_levels = [(code, name) for code, name in settings.LEVEL_CHOICES if code in division_levels]
    else:
        accessible_levels = []
    
    accessible_level_codes = [code for code, name in accessible_levels]
    
    # Recent sessions (filtered by accessible levels)
    recent_sessions = AttendanceSession.objects.filter(
        school=request.school,
        level__in=accessible_level_codes
    ).select_related('term', 'marked_by').order_by('-date')[:10]
    
    # Today's sessions (filtered by accessible levels)
    today_sessions = AttendanceSession.objects.filter(
        school=request.school,
        date=today,
        level__in=accessible_level_codes
    ).select_related('term')
    
    # Get classes that need marking today
    marked_today = list(today_sessions.values_list('level', flat=True))
    pending_levels = [code for code, name in accessible_levels if code not in marked_today]
    
    context = {
        'title': _('Attendance Dashboard'),
        'current_term': current_term,
        'recent_sessions': recent_sessions,
        'today_sessions': today_sessions,
        'pending_levels': [(code, dict(accessible_levels).get(code, code)) for code in pending_levels],
        'today': today,
        'user_division': request.user.division if hasattr(request.user, 'division') else None,
    }
    return render(request, 'attendance/dashboard.html', context)


@login_required
@lecturer_required
def save_attendance_ajax(request):
    """AJAX endpoint to save individual student attendance"""
    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        status = request.POST.get('status', PRESENT)
        remarks = request.POST.get('remarks', '')
        attendance_date_str = request.POST.get('date')
        level_code = request.POST.get('level')
        
        attendance_date = parse_date(attendance_date_str) if attendance_date_str else date.today()
        current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
        
        if not current_term:
            return JsonResponse({'status': 'error', 'message': _("No active term found.")}, status=400)
            
        student = get_object_or_404(Student, id=student_id, student__school=request.school)
        
        # Create or update session for this date/level if it doesn't exist
        session, created = AttendanceSession.objects.get_or_create(
            school=request.school,
            term=current_term,
            level=level_code,
            date=attendance_date,
            defaults={'marked_by': request.user}
        )
        
        # Save individual record
        Attendance.objects.update_or_create(
            student=student,
            date=attendance_date,
            school=request.school,
            subject=None,
            defaults={
                'status': status,
                'remarks': remarks,
                'recorded_by': request.user,
            }
        )
        
        return JsonResponse({
            'status': 'success', 
            'message': _("Attendance for {} recorded as {}.").format(student.student.get_full_name, status)
        })
        
    return JsonResponse({'status': 'error', 'message': _("Invalid request method.")}, status=405)


@login_required
@lecturer_required  
def mark_attendance(request, level=None):
    """Mark attendance for a class - updated to facilitate AJAX workflow"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    if not current_term:
        messages.error(request, _("No active term found."))
        return redirect('attendance_dashboard')
    
    attendance_date_str = request.GET.get('date')
    attendance_date = parse_date(attendance_date_str) if attendance_date_str else date.today()
    
    if not attendance_date:
        attendance_date = date.today()
    
    # Get students for this level who haven't been marked yet for this date
    # (unless they are editing an existing record, but user wants them "gone")
    marked_student_ids = Attendance.objects.filter(
        date=attendance_date,
        student__level=level,
        school=request.school
    ).values_list('student_id', flat=True)
    
    show_all = request.GET.get('show_all') == 'true'
    
    students_qs = Student.objects.filter(
        level=level,
        student__school=request.school
    ).select_related('student')
    
    if not show_all:
        students = students_qs.exclude(id__in=marked_student_ids).order_by('student__last_name', 'student__first_name')
    else:
        students = students_qs.order_by('student__last_name', 'student__first_name')
        
    if request.method == 'POST':
        # Legacy support for bulk save if JS is disabled
        session, created = AttendanceSession.objects.get_or_create(
            school=request.school,
            term=current_term,
            level=level,
            date=attendance_date,
            defaults={'marked_by': request.user}
        )
        
        for student in students_qs:
            status = request.POST.get(f'status_{student.id}')
            if status: # Only save if status provided in POST
                remarks = request.POST.get(f'remarks_{student.id}', '')
                Attendance.objects.update_or_create(
                    student=student,
                    date=attendance_date,
                    school=request.school,
                    subject=None,
                    defaults={
                        'status': status,
                        'remarks': remarks,
                        'recorded_by': request.user,
                    }
                )
        
        messages.success(request, _("Attendance saved successfully!"))
        return redirect('attendance_dashboard')
    
    # Load existing attendance if already marked
    existing_attendance = {}
    existing_records = Attendance.objects.filter(
        date=attendance_date,
        student__in=students_qs,
        school=request.school
    )
    for record in existing_records:
        existing_attendance[record.student_id] = record
    
    context = {
        'title': _('Mark Attendance'),
        'level': level,
        'level_name': dict(settings.LEVEL_CHOICES).get(level, level),
        'students': students,
        'marked_count': len(marked_student_ids),
        'total_count': students_qs.count(),
        'attendance_date': attendance_date,
        'existing_attendance': existing_attendance,
        'current_term': current_term,
        'show_all': show_all,
    }
    return render(request, 'attendance/mark_attendance.html', context)


@login_required
def attendance_reports(request):
    """View attendance reports with filters"""
    # Default: last 30 days
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Filter parameters
    filter_level = request.GET.get('level', '')
    filter_start_str = request.GET.get('start_date')
    filter_end_str = request.GET.get('end_date')
    
    filter_start = parse_date(filter_start_str) if filter_start_str else start_date
    filter_end = parse_date(filter_end_str) if filter_end_str else end_date
    
    # Fallback if parsing fails
    if not filter_start: filter_start = start_date
    if not filter_end: filter_end = end_date
    
    filter_student = request.GET.get('student_id', '')
    
    # Build query
    records = Attendance.objects.filter(
        school=request.school,
        date__range=[filter_start, filter_end]
    ).select_related('student', 'student__student')
    
    if filter_level:
        records = records.filter(student__level=filter_level)
    
    if filter_student:
        records = records.filter(student_id=filter_student)
    
    # Summary statistics
    total_records = records.count()
    present_count = records.filter(status=PRESENT).count()
    absent_count = records.filter(status=ABSENT).count()
    
    context = {
        'title': _('Attendance Reports'),
        'records': records.order_by('-date', 'student__student__last_name')[:200],  # Limit for performance
        'filter_level': filter_level,
        'filter_start': filter_start,
        'filter_end': filter_end,
        'filter_student': filter_student,
        'total_records': total_records,
        'present_count': present_count,
        'absent_count': absent_count,
        'levels': settings.LEVEL_CHOICES,
    }
    return render(request, 'attendance/reports.html', context)


def get_weekly_attendance_data(term, full_records):
    """Generates a weekly grouped attendance list for the calendar view."""
    weekly_data = []
    if not term or not term.start_date or not term.end_date:
        return weekly_data
        
    records_dict = {record.date: record for record in full_records}
    
    # Find the Monday of the start week
    start_date = term.start_date
    week_start = start_date - timedelta(days=start_date.weekday())
    
    # End date is either term end or today (to not show pending for future dates)
    end_date = min(term.end_date, timezone.now().date())
    
    current_week_start = week_start
    week_num = 1
    
    while current_week_start <= end_date:
        days = []
        for i in range(5):  # Monday to Friday
            current_day = current_week_start + timedelta(days=i)
            
            # Don't show padding days after the end date
            if current_day > end_date:
                continue
                
            record = records_dict.get(current_day)
            
            # Default to Pending
            status = 'Pending'
            if record:
                status = record.status
            elif current_day < term.start_date:
                status = 'Not Started'
                
            days.append({
                'date': current_day,
                'status': status,
                'record': record
            })
            
        if days:
            weekly_data.append({
                'week_num': week_num,
                'start_date': days[0]['date'],
                'end_date': days[-1]['date'],
                'days': days
            })
            
        current_week_start += timedelta(days=7)
        week_num += 1
        
    # Reverse to show newest weeks first
    weekly_data.reverse()
    return weekly_data


@login_required
@student_required
def student_attendance_view(request):
    """Student views their own attendance"""
    student = get_object_or_404(Student, student__pk=request.user.id, student__school=request.school)
    
    terms = Term.objects.filter(school=request.school).order_by('-year', '-term')
    term_id = request.GET.get('term_id')
    
    if term_id:
        selected_term = get_object_or_404(Term, id=term_id, school=request.school)
    else:
        selected_term = terms.filter(is_current_term=True).first()
        if not selected_term:
            selected_term = terms.first()
            
    full_records = Attendance.objects.none()
    weekly_data = []
    total = present = absent = attendance_rate = 0
    
    if selected_term:
        # Get attendance records for selected term
        full_records = Attendance.objects.filter(
            student=student,
            school=request.school
        )
        if selected_term.start_date and selected_term.end_date:
            full_records = full_records.filter(date__range=(selected_term.start_date, selected_term.end_date))
            
        full_records = full_records.order_by('-date')
        
        # Calculate statistics from full term records
        total = full_records.count()
        present = full_records.filter(status=PRESENT).count()
        absent = full_records.filter(status=ABSENT).count()
        attendance_rate = round((present / total * 100), 1) if total > 0 else 0
        
        # Generate weekly data
        weekly_data = get_weekly_attendance_data(selected_term, full_records)
    
    # Limit for plain display if not using weekly
    records = full_records[:50]
    
    context = {
        'title': _('My Attendance'),
        'student': student,
        'records': records,
        'weekly_data': weekly_data,
        'selected_term': selected_term,
        'terms': terms,
        'total': total,
        'present': present,
        'absent': absent,
        'attendance_rate': attendance_rate,
        'current_term': selected_term,  # For backward compatibility using `current_term`
    }
    return render(request, 'attendance/student_view.html', context)


@login_required
def parent_attendance_view(request):
    """Parent views their ward's attendance"""
    if not request.user.is_parent:
        messages.error(request, _("Access denied. Parent account required."))
        return redirect('home')
    
    parent = get_object_or_404(Parent, user=request.user)
    student = parent.student
    
    if not student:
        messages.error(request, _("No student linked to this parent account."))
        return redirect('home')
        
    terms = Term.objects.filter(school=request.school).order_by('-year', '-term')
    term_id = request.GET.get('term_id')
    
    if term_id:
        selected_term = get_object_or_404(Term, id=term_id, school=request.school)
    else:
        selected_term = terms.filter(is_current_term=True).first()
        if not selected_term:
            selected_term = terms.first()
            
    full_records = Attendance.objects.none()
    weekly_data = []
    total = present = absent = attendance_rate = 0
    
    if selected_term:
        # Get attendance records for selected term
        full_records = Attendance.objects.filter(
            student=student,
            school=request.school
        )
        if selected_term.start_date and selected_term.end_date:
            full_records = full_records.filter(date__range=(selected_term.start_date, selected_term.end_date))
            
        full_records = full_records.order_by('-date')
        
        # Calculate statistics from full records
        total = full_records.count()
        present = full_records.filter(status=PRESENT).count()
        absent = full_records.filter(status=ABSENT).count()
        attendance_rate = round((present / total * 100), 1) if total > 0 else 0
        
        # Generate weekly data
        weekly_data = get_weekly_attendance_data(selected_term, full_records)
    
    # Limit for display
    records = full_records[:50]
    
    context = {
        'title': _('Ward Attendance'),
        'student': student,
        'records': records,
        'weekly_data': weekly_data,
        'selected_term': selected_term,
        'terms': terms,
        'total': total,
        'present': present,
        'absent': absent,
        'attendance_rate': attendance_rate,
        'current_term': selected_term, # For backward compatibility
    }
    return render(request, 'attendance/parent_view.html', context)
