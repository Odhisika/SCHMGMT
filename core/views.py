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
from .forms import SemesterForm, NewsAndEventsForm
from .models import NewsAndEvents, ActivityLog, Semester


# ########################################################
# News & Events
# ########################################################
@login_required
def home_view(request):
    user = request.user
    
    # Base filter: School
    items = NewsAndEvents.objects.filter(school=request.school)
    
    if not user.is_superuser and not user.is_school_admin:
        # 1. Define Role Filter
        if user.is_teacher or user.is_lecturer:
            role_q = Q(target_role__in=['ALL', 'TEACHERS'])
        elif user.is_student:
            role_q = Q(target_role__in=['ALL', 'STUDENTS'])
        elif user.is_parent:
            role_q = Q(target_role__in=['ALL', 'PARENTS'])
        else: # user, etc
            role_q = Q(target_role='ALL')
            
        # 2. Define Division Filter
        # If post has no division (None/""), it's for everyone. If it has a division, user must match it.
        # Note: If user.division is None, they only see Global posts.
        if user.division:
            div_q = Q(target_division__isnull=True) | Q(target_division="") | Q(target_division=user.division)
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

    items = items.order_by("-updated_date")
    context = {
        "title": "News & Events",
        "items": items,
    }
    return render(request, "core/index.html", context)


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

    
    context = {
        "student_count": student_count,
        "lecturer_count": teacher_count,
        "superuser_count": superuser_count,
        "males_count": males_count,
        "females_count": females_count,
        "logs": logs,
        "selected_division": division,
        
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


@login_required
@lecturer_required
def semester_add_view(request):
    if request.method == "POST":
        form = SemesterForm(request.POST)
        if form.is_valid():
            # Use 'is_current_term' as defined in Term/TermForm model
            if form.cleaned_data.get("is_current_term"):
                unset_current_semester(request.school)
            
            term = form.save(commit=False)
            term.school = request.school
            term.save()
            
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
            if form.cleaned_data.get("is_current_term"):
                unset_current_semester(request.school)
            form.save()
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
