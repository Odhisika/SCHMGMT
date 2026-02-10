from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils.dateparse import parse_date
from datetime import date, timedelta
from decimal import Decimal

from accounts.decorators import lecturer_required, student_required, admin_required
from accounts.models import Student
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
def mark_attendance(request, level=None):
    """Mark attendance for a class"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    if not current_term:
        messages.error(request, _("No active term found."))
        return redirect('attendance_dashboard')
    
    attendance_date_str = request.GET.get('date')
    attendance_date = parse_date(attendance_date_str) if attendance_date_str else date.today()
    
    if not attendance_date:
        attendance_date = date.today()
    
    # Get students for this level
    students = Student.objects.filter(
        level=level,
        student__school=request.school
    ).select_related('student').order_by('student__last_name', 'student__first_name')
    
    if request.method == 'POST':
        # Check if session already exists
        session, created = AttendanceSession.objects.get_or_create(
            school=request.school,
            term=current_term,
            level=level,
            date=attendance_date,
            defaults={'marked_by': request.user}
        )
        
        # Process attendance for each student
        for student in students:
            status = request.POST.get(f'status_{student.id}', PRESENT)
            remarks = request.POST.get(f'remarks_{student.id}', '')
            
            Attendance.objects.update_or_create(
                student=student,
                date=attendance_date,
                school=request.school,
                subject=None,  # Daily attendance, not subject-specific
                defaults={
                    'status': status,
                    'remarks': remarks,
                    'recorded_by': request.user,
                }
            )
        
        messages.success(request, _("Attendance marked successfully!"))
        return redirect('attendance_dashboard')
    
    # Load existing attendance if already marked
    existing_attendance = {}
    existing_records = Attendance.objects.filter(
        date=attendance_date,
        student__in=students,
        school=request.school
    )
    for record in existing_records:
        existing_attendance[record.student_id] = record
    
    context = {
        'title': _('Mark Attendance'),
        'level': level,
        'level_name': dict(settings.LEVEL_CHOICES).get(level, level),
        'students': students,
        'attendance_date': attendance_date,
        'existing_attendance': existing_attendance,
        'current_term': current_term,
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


@login_required
@student_required
def student_attendance_view(request):
    """Student views their own attendance"""
    student = get_object_or_404(Student, student__pk=request.user.id, student__school=request.school)
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    
    # Get attendance records for current term
    records = Attendance.objects.filter(
        student=student,
        school=request.school
    ).order_by('-date')[:50]  # Last 50 records
    
    # Calculate statistics
    total = records.count()
    present = records.filter(status=PRESENT).count()
    absent = records.filter(status=ABSENT).count()
    attendance_rate = round((present / total * 100), 1) if total > 0 else 0
    
    context = {
        'title': _('My Attendance'),
        'student': student,
        'records': records,
        'total': total,
        'present': present,
        'absent': absent,
        'attendance_rate': attendance_rate,
        'current_term': current_term,
    }
    return render(request, 'attendance/student_view.html', context)
