from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils.dateparse import parse_date
from datetime import date, timedelta
from decimal import Decimal
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Sum
from django.utils import timezone

from accounts.decorators import lecturer_required, student_required, admin_required
from accounts.models import Student, Parent
from core.models import Term
from course.models import CourseAllocation
from .models import Attendance, AttendanceSession, AttendanceSummary, PRESENT, ABSENT


def _attendance_levels_for_user(user):
    """Return attendance levels this user can view.

    This controls read access only. Marking is restricted separately to
    teachers with an allocated course in the class.
    """
    all_levels = settings.LEVEL_CHOICES
    valid_level_codes = {code for code, _ in all_levels}

    if user.is_superuser or user.is_school_admin:
        return list(all_levels)

    accessible = []
    if user.is_teacher or user.is_lecturer:
        division_levels = set(user.get_division_levels())
        accessible = [(code, name) for code, name in all_levels if code in division_levels]

    if user.is_class_teacher:
        assigned_level = user.assigned_level
        already_included = {code for code, _ in accessible}
        if assigned_level in valid_level_codes and assigned_level not in already_included:
            accessible.append((assigned_level, dict(all_levels)[assigned_level]))

    return accessible


def _teacher_markable_level_codes(user, school):
    """Level codes where this user has an allocated course in their division."""
    if user.is_superuser or user.is_school_admin:
        return set()
    if not (user.is_teacher or user.is_lecturer):
        return set()
    if not user.division:
        return set()

    division_levels = set(user.get_division_levels())
    if not division_levels:
        return set()

    return set(
        CourseAllocation.objects.filter(
            teacher=user,
            courses__school=school,
            courses__level__in=division_levels,
        ).values_list('courses__level', flat=True)
    )


def _attendance_marking_levels_for_user(user, school):
    """Levels this user is allowed to mark, based on course allocations."""
    markable_levels = _teacher_markable_level_codes(user, school)
    return [
        (code, name)
        for code, name in settings.LEVEL_CHOICES
        if code in markable_levels
    ]


def _session_lock_error(user, session):
    """Return a reason the user cannot mark an existing session, if any."""
    if session is None or session.marked_by_id == user.id:
        return None

    owner = session.marked_by.get_full_name if session.marked_by_id else ""
    if owner:
        return _(
            "Attendance for this class has already been marked by %(teacher)s. "
            "Only that teacher can update it."
        ) % {"teacher": owner}
    return _(
        "Attendance for this class has already been marked. "
        "Only the teacher who marked it can update it."
    )


def _term_for_date(school, target_date):
    """Find the school term that contains ``target_date``.

    Terms with missing start/end dates cannot be matched by range, so the
    current term is used as a fallback for those legacy records.
    """
    term = (
        Term.objects.filter(
            school=school,
            start_date__isnull=False,
            end_date__isnull=False,
            start_date__lte=target_date,
            end_date__gte=target_date,
        )
        .order_by("-is_current_term", "-year", "-term")
        .first()
    )
    if term:
        return term

    current_term = Term.objects.filter(school=school, is_current_term=True).first()
    if current_term and (current_term.start_date is None or current_term.end_date is None):
        return current_term

    return None


def _validate_attendance_date(user, school, target_date):
    """Return ``(term, error_message)`` for a requested attendance date."""
    if target_date > timezone.localdate():
        return None, _("Attendance cannot be marked for a future date.")

    term = _term_for_date(school, target_date)
    if term is None:
        return None, _(
            "No term covers %(date)s. Ask an administrator to check the term dates."
        ) % {"date": target_date}

    if not (user.is_superuser or user.is_school_admin):
        current_term = Term.objects.filter(school=school, is_current_term=True).first()
        if current_term is None:
            return None, _("No active term found. Ask an administrator to set up the term dates.")
        if current_term.pk != term.pk:
            return None, _(
                "Only attendance for the current term can be edited. "
                "Ask a school administrator to correct older records."
            )

    return term, None


@login_required
@lecturer_required
def attendance_dashboard(request):
    """Attendance overview for teachers/admins - filtered by division"""
    target_level = request.GET.get('level')
    target_date_str = request.GET.get('date')
    if target_level and target_date_str:
        allowed_levels = {code for code, _ in _attendance_levels_for_user(request.user)}
        target_date = parse_date(target_date_str)
        if target_level in allowed_levels and target_date:
            url = reverse('attendance:mark_attendance', args=[target_level])
            return redirect(f"{url}?date={target_date.isoformat()}")
        messages.error(request, _("Choose a valid class and date."))
        return redirect('attendance:dashboard')

    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    today = timezone.localdate()
    
    view_levels = _attendance_levels_for_user(request.user)
    view_level_codes = [code for code, name in view_levels]
    marking_levels = _attendance_marking_levels_for_user(request.user, request.school)
    
    # Recent sessions (filtered by levels this user can view)
    recent_sessions = AttendanceSession.objects.filter(
        school=request.school,
        level__in=view_level_codes
    ).select_related('term', 'marked_by').order_by('-date')[:10]
    
    # Today's sessions (filtered by levels this user can view)
    today_sessions = AttendanceSession.objects.filter(
        school=request.school,
        date=today,
        level__in=view_level_codes
    ).select_related('term')
    
    # Only teachers with an allocated course can start a new register.
    marked_today = set(today_sessions.values_list('level', flat=True))
    pending_levels = [
        (code, name) for code, name in marking_levels if code not in marked_today
    ]
    
    context = {
        'title': _('Attendance Dashboard'),
        'current_term': current_term,
        'recent_sessions': recent_sessions,
        'today_sessions': today_sessions,
        'pending_levels': pending_levels,
        'marking_levels': marking_levels,
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
        
        attendance_date = parse_date(attendance_date_str) if attendance_date_str else timezone.localdate()
        if not attendance_date:
            return JsonResponse(
                {'status': 'error', 'message': _("Invalid attendance date.")}, status=400
            )

        attendance_term, date_error = _validate_attendance_date(
            request.user, request.school, attendance_date
        )
        if date_error:
            return JsonResponse({'status': 'error', 'message': date_error}, status=400)
            
        if request.user.is_superuser or request.user.is_school_admin:
            return JsonResponse(
                {
                    'status': 'error',
                    'message': _(
                        "School administrators can view attendance records but cannot mark them."
                    ),
                },
                status=403,
            )

        student = get_object_or_404(
            Student.objects.select_related('student'),
            id=student_id,
            student__school=request.school,
        )
        allowed_levels = {
            code
            for code, _ in _attendance_marking_levels_for_user(
                request.user, request.school
            )
        }
        if student.level not in allowed_levels or level_code != student.level:
            return JsonResponse(
                {
                    'status': 'error',
                    'message': _(
                        "You can only mark attendance for classes where you have an allocated course."
                    ),
                },
                status=403,
            )

        valid_statuses = {choice[0] for choice in Attendance._meta.get_field('status').choices}
        if status not in valid_statuses:
            return JsonResponse({'status': 'error', 'message': _("Invalid attendance status.")}, status=400)
        
        # The first teacher to mark a class/date claims the register. Other
        # teachers can still view it, but only the owner may add or change marks.
        session, created = AttendanceSession.objects.get_or_create(
            school=request.school,
            level=student.level,
            date=attendance_date,
            defaults={'term': attendance_term, 'marked_by': request.user}
        )
        lock_error = _session_lock_error(request.user, session)
        if lock_error:
            return JsonResponse({'status': 'error', 'message': lock_error}, status=403)
        
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
    """View a class register and let allocated teachers mark it."""
    view_levels = {code for code, _ in _attendance_levels_for_user(request.user)}
    if level not in view_levels:
        return HttpResponseForbidden(_("You can only access attendance for your assigned class or division."))

    attendance_date_str = request.GET.get('date') or request.POST.get('date')
    attendance_date = parse_date(attendance_date_str) if attendance_date_str else timezone.localdate()
    if not attendance_date:
        attendance_date = timezone.localdate()

    attendance_term, date_error = _validate_attendance_date(
        request.user, request.school, attendance_date
    )
    if date_error:
        messages.error(request, date_error)
        return redirect('attendance:dashboard')

    today = timezone.localdate()

    existing_session = AttendanceSession.objects.filter(
        school=request.school,
        level=level,
        date=attendance_date,
    ).select_related('marked_by').first()

    marking_levels = {
        code
        for code, _ in _attendance_marking_levels_for_user(
            request.user, request.school
        )
    }
    can_mark = level in marking_levels
    read_only_reason = None
    if request.user.is_superuser or request.user.is_school_admin:
        can_mark = False
        read_only_reason = _(
            "School administrators can view attendance records but cannot mark them."
        )
    elif not can_mark:
        read_only_reason = _(
            "You can only mark attendance for classes where you have an allocated course."
        )
    else:
        lock_error = _session_lock_error(request.user, existing_session)
        if lock_error:
            can_mark = False
            read_only_reason = lock_error

    if request.method == 'POST' and not can_mark:
        return HttpResponseForbidden(
            read_only_reason or _("You cannot mark attendance for this class.")
        )

    # Read-only views show the whole class so administrators can see every
    # recorded status, while teachers only see their remaining students.
    show_all = request.GET.get('show_all') == 'true' or not can_mark

    # Get students for this level who haven't been marked yet for this date
    # (unless they are editing an existing record, but user wants them "gone")
    marked_student_ids = Attendance.objects.filter(
        date=attendance_date,
        student__level=level,
        school=request.school
    ).values_list('student_id', flat=True)
    
    students_qs = Student.objects.filter(
        level=level,
        student__school=request.school,
        status=STUDENT_STATUS_ACTIVE,
    ).select_related('student')
    
    if not show_all:
        students = students_qs.exclude(id__in=marked_student_ids).order_by('student__last_name', 'student__first_name')
    else:
        students = students_qs.order_by('student__last_name', 'student__first_name')
        
    if request.method == 'POST':
        # Legacy support for bulk save if JS is disabled
        session, created = AttendanceSession.objects.get_or_create(
            school=request.school,
            level=level,
            date=attendance_date,
            defaults={'term': attendance_term, 'marked_by': request.user}
        )
        lock_error = _session_lock_error(request.user, session)
        if lock_error:
            messages.error(request, lock_error)
            return redirect('attendance:dashboard')
        existing_session = session
        
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
        return redirect('attendance:dashboard')
    
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
        'attendance_term': attendance_term,
        'existing_session': existing_session,
        'can_mark': can_mark,
        'read_only_reason': read_only_reason,
        'today': today,
        'is_late': attendance_date < today,
        'late_days': (today - attendance_date).days,
        'show_all': show_all,
    }
    return render(request, 'attendance/mark_attendance.html', context)


@login_required
def attendance_reports(request):
    """View attendance reports with filters"""
    accessible_levels = _attendance_levels_for_user(request.user)
    accessible_level_codes = [code for code, _ in accessible_levels]
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
        date__range=[filter_start, filter_end],
        student__level__in=accessible_level_codes,
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
        'levels': accessible_levels,
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
