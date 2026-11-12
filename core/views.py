from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import json

from accounts.decorators import admin_required, lecturer_required
from accounts.models import User, Student
from course.models import Program, Course
from .forms import SemesterForm, NewsAndEventsForm, TermWeekForm
from .models import NewsAndEvents, ActivityLog, Semester, TermWeek
from .models import Notification
from .notifications import notify, notify_students, notify_parents


# ########################################################
# News & Events
# ########################################################
def get_visible_posts(user, school):
    """Return the news/events that ``user`` is allowed to see in ``school``."""
    items = NewsAndEvents.objects.filter(school=school)

    if not user.is_superuser and not user.is_school_admin:
        # 1. Define Role Filter
        if user.is_teacher or user.is_lecturer:
            role_q = Q(target_role__in=['ALL', 'TEACHERS'])
        elif user.is_student:
            role_q = Q(target_role__in=['ALL', 'STUDENTS'])
        elif user.is_parent:
            role_q = Q(target_role__in=['ALL', 'PARENTS'])
        else:  # user, etc
            role_q = Q(target_role='ALL')

        # 2. Define Division Filter
        # If post has no division (None/""), it's for everyone. If it has a
        # division, the user must match it.
        if user.division:
            div_q = (
                Q(target_division__isnull=True)
                | Q(target_division="")
                | Q(target_division=user.division)
            )
        else:
            # Users with no division (e.g. some staff) only see global posts
            div_q = Q(target_division__isnull=True) | Q(target_division="")

        # 3. Combine Logic
        # Show if:
        # (It is a Targeted Specific Post AND User is in list)
        # OR
        # (It is NOT Specific AND Matches Division AND Matches Role)
        specific_q = Q(target_role='SPECIFIC') & Q(specific_users=user)
        general_q = ~Q(target_role='SPECIFIC') & div_q & role_q

        items = items.filter(specific_q | general_q).distinct()

    return items


@login_required
def home_view(request):
    items = get_visible_posts(request.user, request.school).order_by("-updated_date")

    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    term_weeks = TermWeek.objects.filter(term=current_term, is_active=True).order_by("week_number") if current_term else []

    current_week = None
    if current_term and current_term.start_date:
        today = timezone.now().date()
        days_since_start = (today - current_term.start_date).days
        if days_since_start >= 0:
            week_num = (days_since_start // 7) + 1
            current_week = term_weeks.filter(week_number=week_num).first() if term_weeks else None
    if not current_week and term_weeks:
        current_week = term_weeks.first()

    show_all = request.GET.get("show_all") == "1"

    context = {
        "title": "News & Events",
        "items": items,
        "current_term": current_term,
        "term_weeks": term_weeks,
        "current_week": current_week,
        "show_all": show_all,
    }
    return render(request, "core/index.html", context)


@login_required
def post_detail(request, pk):
    """Show the full contents of a news item or event for the current user."""
    post = get_object_or_404(
        get_visible_posts(request.user, request.school),
        pk=pk,
    )
    return render(request, "core/post_detail.html", {
        "title": post.title,
        "post": post,
    })


@login_required
@admin_required
def dashboard_view(request):
    division = request.GET.get('division', 'ALL')
    dashboard_school = request.school
    
    # 1. Base QuerySets
    student_qs = Student.objects.filter(student__school=dashboard_school, student__is_active=True)
    teacher_qs = User.objects.filter(school=dashboard_school, is_active=True).filter(Q(is_lecturer=True) | Q(is_teacher=True))
    
    # 2. Apply Division Filters
    if division in [settings.DIVISION_NURSERY, settings.DIVISION_PRIMARY, settings.DIVISION_JHS]:
        levels = settings.DIVISION_LEVEL_MAPPING.get(division, [])
        student_qs = student_qs.filter(level__in=levels)
        teacher_qs = teacher_qs.filter(division=division)
        
        # Filter logs? Maybe just keep logs global or simple
        logs = ActivityLog.objects.filter(school=request.school).order_by("-created_at")[:10]
    else:
        # ALL
        logs = ActivityLog.objects.filter(school=request.school).order_by("-created_at")[:10]

    # 3. Compute Counts
    student_count = student_qs.count()
    teacher_count = teacher_qs.count()
    superuser_count = User.objects.filter(is_superuser=True).count() # Global staff check
    
    # 4. Chart Data Preparation
    
    # A. Demographics (Gender)
    males_count = student_qs.filter(student__gender="M").count()
    females_count = student_qs.filter(student__gender="F").count()
    
    # B. Staffing (Teachers per Department)
    # Group by department name. handle null department.
    dept_counts = {}
    for t in teacher_qs.select_related('department'):
        dept_name = t.department.title if t.department else "General"
        dept_counts[dept_name] = dept_counts.get(dept_name, 0) + 1
    
    staffing_labels = list(dept_counts.keys())
    staffing_data = list(dept_counts.values())
    
    # C. Enrollment (Students per Level)
    # Determine levels to show
    if division == 'ALL':
        # Show broad categories? Or all levels? 
        # All levels might be too many (approx 13). Let's try grouping by Division if ALL?
        # Or just show all. Let's show all for detail.
        pass
    
    level_counts = {}
    # Use the levels from settings to ensure order
    target_levels = []
    if division != 'ALL':
        target_levels = settings.DIVISION_LEVEL_MAPPING.get(division, [])
    else:
        for d in [settings.DIVISION_NURSERY, settings.DIVISION_PRIMARY, settings.DIVISION_JHS]:
             target_levels.extend(settings.DIVISION_LEVEL_MAPPING.get(d, []))
             
    # Default 0
    for l in target_levels:
        level_counts[l] = 0
        
    # Process
    stats = student_qs.values('level').annotate(count=Count('id'))
    for s in stats:
        if s['level'] in level_counts:
            level_counts[s['level']] = s['count']
            
    enrollment_labels = list(level_counts.keys())
    enrollment_data = list(level_counts.values())
    
    # D. Traffic (User Growth - Last 6 Months)
    # Students vs Teachers added
    today = timezone.now().date()
    traffic_labels = []
    student_growth = []
    teacher_growth = []
    
    for i in range(5, -1, -1):
        # Get month name and year
        start_date = (today.replace(day=1) - timedelta(days=30*i)).replace(day=1)
        # End date is start of next month
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)
            
        label = start_date.strftime("%B")
        traffic_labels.append(label)
        
        # Count created in this range
        s_c = student_qs.filter(student__date_joined__gte=start_date, student__date_joined__lt=end_date).count()
        t_c = teacher_qs.filter(date_joined__gte=start_date, date_joined__lt=end_date).count()
        
        student_growth.append(s_c)
        teacher_growth.append(t_c)

    
    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    term_weeks = TermWeek.objects.filter(term=current_term, is_active=True).order_by("week_number") if current_term else []

    context = {
        "student_count": student_count,
        "lecturer_count": teacher_count,
        "superuser_count": superuser_count,
        "males_count": males_count,
        "females_count": females_count,
        "logs": logs,
        "selected_division": division,
        "current_term": current_term,
        "term_weeks": term_weeks,
        
        # Chart JSON
        "traffic_data": json.dumps({
            "labels": traffic_labels,
            "students": student_growth,
            "teachers": teacher_growth
        }),
        "enrollment_data": json.dumps({
            "labels": enrollment_labels,
            "data": enrollment_data
        }),
        "staffing_data": json.dumps({
            "labels": staffing_labels,
            "data": staffing_data
        }),
        "gender_data": json.dumps({
            "labels": ["Male", "Female"],
            "data": [males_count, females_count]
        })
    }
    return render(request, "core/dashboard.html", context)


@login_required
def post_add(request):
    if request.method == "POST":
        form = NewsAndEventsForm(request.POST)
        title = form.cleaned_data.get("title", "Post") if form.is_valid() else None
        if form.is_valid():
            instance = form.save(commit=False)
            instance.school = request.school
            instance.save()
            form.save_m2m()
            if instance.target_role == "SPECIFIC":
                for recipient in instance.specific_users.filter(school=request.school):
                    notify(
                        school=request.school,
                        recipient=recipient,
                        title=instance.title or "School announcement",
                        message=instance.summary or "",
                        link="/",
                        actor=request.user,
                    )
            else:
                audience = {
                    "ALL": Notification.AUDIENCE_ALL,
                    "TEACHERS": Notification.AUDIENCE_TEACHER,
                    "STUDENTS": Notification.AUDIENCE_STUDENT,
                    "PARENTS": Notification.AUDIENCE_PARENT,
                }.get(instance.target_role)
                if audience:
                    notify(
                        school=request.school,
                        audience=audience,
                        division=instance.target_division or "",
                        title=instance.title or "School announcement",
                        message=instance.summary or "",
                        link="/",
                        actor=request.user,
                    )
            messages.success(request, f"{title} has been uploaded.")
            return redirect("home")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = NewsAndEventsForm()
    return render(request, "core/post_add.html", {"title": "Add Post", "form": form})


@login_required
@lecturer_required
def edit_post(request, pk):
    instance = get_object_or_404(NewsAndEvents, pk=pk)
    if request.method == "POST":
        form = NewsAndEventsForm(request.POST, instance=instance)
        title = form.cleaned_data.get("title", "Post") if form.is_valid() else None
        if form.is_valid():
            form.save()
            messages.success(request, f"{title} has been updated.")
            return redirect("home")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = NewsAndEventsForm(instance=instance)
    return render(request, "core/post_add.html", {"title": "Edit Post", "form": form})


@login_required
@lecturer_required
def delete_post(request, pk):
    post = get_object_or_404(NewsAndEvents, pk=pk)
    post_title = post.title
    post.delete()
    messages.success(request, f"{post_title} has been deleted.")
    return redirect("home")


# ########################################################
# Semester (Term)
# ########################################################
@login_required
@lecturer_required
def semester_list_view(request):
    # Updated to filter by school and use correct field names
    semesters = Semester.objects.filter(school=request.school).order_by("-is_current_term", "-term")
    return render(request, "core/semester_list.html", {"semesters": semesters})


def _is_truthy(value):
    """Interpret values submitted by ``TermForm``'s Yes/No field."""
    return str(value).strip().lower() in ("true", "1", "yes", "on")


@login_required
@lecturer_required
def semester_add_view(request):
    if request.method == "POST":
        form = SemesterForm(request.POST)
        if form.is_valid():
            # Use 'is_current_term' as defined in Term/TermForm model
            if _is_truthy(form.cleaned_data.get("is_current_term")):
                unset_current_semester(request.school)
            
            term = form.save(commit=False)
            term.school = request.school
            term.save()
            if term.result_released:
                title = f"{term.get_term_display()} {term.year} results are available"
                notify_students(
                    request.school, title, "Your term results are ready to view.",
                    link="/result/report-cards/",
                    notification_type=Notification.TYPE_SUCCESS, actor=request.user,
                )
                notify_parents(
                    request.school, title,
                    "Term results for your linked student are ready to view.",
                    link="/result/report-cards/",
                    notification_type=Notification.TYPE_SUCCESS, actor=request.user,
                )
            
            messages.success(request, "Semester added successfully.")
            return redirect("semester_list")
    else:
        form = SemesterForm()
    return render(request, "core/semester_update.html", {"form": form})


@login_required
@lecturer_required
def semester_update_view(request, pk):
    semester = get_object_or_404(Semester, pk=pk, school=request.school)
    if request.method == "POST":
        form = SemesterForm(request.POST, instance=semester)
        if form.is_valid():
            was_released = semester.result_released
            if _is_truthy(form.cleaned_data.get("is_current_term")):
                unset_current_semester(request.school)
            semester = form.save()
            if not was_released and semester.result_released:
                title = f"{semester.get_term_display()} {semester.year} results are available"
                notify_students(
                    request.school,
                    title,
                    "Your term results are ready to view.",
                    link="/result/report-cards/",
                    notification_type=Notification.TYPE_SUCCESS,
                    actor=request.user,
                )
                notify_parents(
                    request.school,
                    title,
                    "Term results for your linked student are ready to view.",
                    link="/result/report-cards/",
                    notification_type=Notification.TYPE_SUCCESS,
                    actor=request.user,
                )
            messages.success(request, "Semester updated successfully!")
            return redirect("semester_list")
    else:
        form = SemesterForm(instance=semester)
    return render(request, "core/semester_update.html", {"form": form})


@login_required
@lecturer_required
def semester_delete_view(request, pk):
    semester = get_object_or_404(Semester, pk=pk, school=request.school)
    if semester.is_current_term:
        messages.error(request, "You cannot delete the current semester.")
    else:
        semester.delete()
        messages.success(request, "Semester successfully deleted.")
    return redirect("semester_list")


def unset_current_semester(school):
    """Unset current semester for a specific school"""
    current_semester = Semester.objects.filter(is_current_term=True, school=school).first()
    if current_semester:
        current_semester.is_current_term = False
        current_semester.save()


# ########################################################
# Term Weeks
# ########################################################
def _fill_week_dates_from_term(week, term):
    """Fill omitted activity dates from the term's calendar week boundaries."""
    if not term.start_date:
        return
    generated_start = term.start_date + timedelta(days=(week.week_number - 1) * 7)
    generated_end = generated_start + timedelta(days=6)
    if term.end_date:
        generated_end = min(generated_end, term.end_date)
    if week.start_date is None:
        week.start_date = generated_start
    if week.end_date is None:
        week.end_date = generated_end


@login_required
@lecturer_required
def term_week_list_view(request, term_pk):
    term = get_object_or_404(Semester, pk=term_pk, school=request.school)
    weeks = TermWeek.objects.filter(term=term).order_by("week_number")
    return render(request, "core/term_week_list.html", {"term": term, "weeks": weeks})


@login_required
@lecturer_required
def term_week_add_view(request, term_pk):
    term = get_object_or_404(Semester, pk=term_pk, school=request.school)
    if request.method == "POST":
        form = TermWeekForm(request.POST, term=term)
        if form.is_valid():
            week = form.save(commit=False)
            week.term = term
            _fill_week_dates_from_term(week, term)
            week.save()
            messages.success(request, f"Week {week.week_number} added successfully.")
            return redirect("term_week_list", term_pk=term.pk)
    else:
        form = TermWeekForm(term=term)
    return render(request, "core/term_week_form.html", {"form": form, "term": term})


@login_required
@lecturer_required
def term_week_edit_view(request, term_pk, pk):
    term = get_object_or_404(Semester, pk=term_pk, school=request.school)
    week = get_object_or_404(TermWeek, pk=pk, term=term)
    if request.method == "POST":
        form = TermWeekForm(request.POST, instance=week, term=term)
        if form.is_valid():
            form.save()
            _fill_week_dates_from_term(week, term)
            week.save(update_fields=["start_date", "end_date"])
            messages.success(request, f"Week {week.week_number} updated.")
            return redirect("term_week_list", term_pk=term.pk)
    else:
        form = TermWeekForm(instance=week, term=term)
    return render(request, "core/term_week_form.html", {"form": form, "term": term, "week": week})


@login_required
@lecturer_required
def term_week_delete_view(request, term_pk, pk):
    term = get_object_or_404(Semester, pk=term_pk, school=request.school)
    week = get_object_or_404(TermWeek, pk=pk, term=term)
    week.delete()
    messages.success(request, f"Week {week.week_number} deleted.")
    return redirect("term_week_list", term_pk=term.pk)


@login_required
@lecturer_required
def term_week_init_view(request, term_pk):
    """Auto-generate weeks from term start_date to end_date (one week per 7 days)"""
    term = get_object_or_404(Semester, pk=term_pk, school=request.school)
    if not term.start_date or not term.end_date:
        messages.error(request, "Set start and end dates for this term first.")
        return redirect("term_week_list", term_pk=term.pk)

    existing = TermWeek.objects.filter(term=term).count()
    if existing > 0:
        messages.warning(request, f"{existing} week(s) already exist. Delete them first to re-initialize.")
        return redirect("term_week_list", term_pk=term.pk)

    delta = (term.end_date - term.start_date).days
    num_weeks = max(1, (delta // 7) + 1)

    for w in range(1, num_weeks + 1):
        TermWeek.objects.create(
            term=term,
            week_number=w,
            start_date=term.start_date + timedelta(days=(w - 1) * 7),
            end_date=min(term.start_date + timedelta(days=(w * 7) - 1), term.end_date),
            activity_type="normal_lesson",
            title=f"Week {w}",
        )

    messages.success(request, f"{num_weeks} week(s) generated from term dates.")
    return redirect("term_week_list", term_pk=term.pk)


from django.http import JsonResponse
from django.conf import settings

@login_required
def get_users_for_targeting(request):
    """AJAX view to fetch users based on division and role"""
    division = request.GET.get('division')
    role = request.GET.get('role', 'ALL')
    query = request.GET.get('q', '')
    
    q_objects = Q()
    
    # Base filter: Active users in this school
    base_qs = User.objects.filter(school=request.school, is_active=True)
    
    # 1. Division Logic
    if division and division != 'ALL':
        # Get levels for this division
        levels = settings.DIVISION_LEVEL_MAPPING.get(division, [])
        
        # Teachers in this division
        teacher_q = Q(division=division) & (Q(is_teacher=True) | Q(is_lecturer=True))
        
        # Students in this division (via level)
        student_q = Q(student__level__in=levels) & Q(is_student=True)
        
        # Combined Division Logic
        if role == 'TEACHERS':
            base_qs = base_qs.filter(teacher_q)
        elif role == 'STUDENTS':
            base_qs = base_qs.filter(student_q)
        else: # ALL in Division
            base_qs = base_qs.filter(teacher_q | student_q)
            
    else: # No division (Whole School)
        if role == 'TEACHERS':
            base_qs = base_qs.filter(Q(is_teacher=True) | Q(is_lecturer=True))
        elif role == 'STUDENTS':
            base_qs = base_qs.filter(is_student=True)
        # else ALL: No extra filter
    
    # 2. Search Logic
    if query:
        base_qs = base_qs.filter(
            Q(username__icontains=query) | 
            Q(first_name__icontains=query) | 
            Q(last_name__icontains=query)
        )
    
    # Limit results
    users = base_qs.order_by('first_name', 'last_name')[:50]
    
    data = [{'id': u.id, 'text': f"{u.get_full_name} ({u.get_user_role})"} for u in users]
    return JsonResponse({'results': data})
