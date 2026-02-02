from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q

from accounts.decorators import admin_required, lecturer_required
from accounts.models import User, Student
from .forms import SemesterForm, NewsAndEventsForm
from .models import NewsAndEvents, ActivityLog, Semester


# ########################################################
# News & Events
# ########################################################
@login_required
def home_view(request):
    # Filter news items by the current school
    items = NewsAndEvents.objects.filter(school=request.school).order_by("-updated_date")
    context = {
        "title": "News & Events",
        "items": items,
    }
    return render(request, "core/index.html", context)


@login_required
@admin_required
def dashboard_view(request):
    # Filter logs by the current school
    logs = ActivityLog.objects.filter(school=request.school).order_by("-created_at")[:10]
    dashboard_school = request.school
    
    # Counts filtered by school
    student_count = User.objects.filter(is_student=True, school=dashboard_school).count()
    teacher_count = User.objects.filter(Q(is_lecturer=True) | Q(is_teacher=True), school=dashboard_school).count()
    superuser_count = User.objects.filter(is_superuser=True).count()
    
    # Gender counts for students in this school
    males_count = Student.objects.filter(student__gender="M", student__school=dashboard_school).count()
    females_count = Student.objects.filter(student__gender="F", student__school=dashboard_school).count()
    
    context = {
        "student_count": student_count,
        "lecturer_count": teacher_count,
        "superuser_count": superuser_count,
        "males_count": males_count,
        "females_count": females_count,
        "logs": logs,
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
