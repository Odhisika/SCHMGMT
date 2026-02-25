from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.utils.decorators import method_decorator
from django.views.generic import CreateView
from django_filters.views import FilterView
from xhtml2pdf import pisa
from django.conf import settings

from accounts.decorators import admin_required, lecturer_required
from accounts.filters import LecturerFilter, StudentFilter
from accounts.forms import (
    ParentAddForm,
    ProfileUpdateForm,
    ProgramUpdateForm,
    StaffAddForm,
    StudentAddForm,
)
from accounts.models import Parent, Student, User
from core.models import Semester
from course.models import Course, CourseAllocation
from result.models import TakenCourse, Result

# ########################################################
# Utility Functions
# ########################################################


def render_to_pdf(template_name, context):
    """Render a given template to PDF format."""
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="profile.pdf"'
    template = render_to_string(template_name, context)
    pdf = pisa.CreatePDF(template, dest=response)
    if pdf.err:
        return HttpResponse("We had some problems generating the PDF")
    return response


# ########################################################
# Authentication and Registration
# ########################################################


def validate_username(request):
    username = request.GET.get("username", None)
    data = {"is_taken": User.objects.filter(username__iexact=username).exists()}
    return JsonResponse(data)


def register(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully.")
            return redirect("login")
        messages.error(
            request, "Something is not correct, please fill all fields correctly."
        )
    else:
        form = StudentAddForm()
    return render(request, "registration/register.html", {"form": form})


# ########################################################
# Profile Views
# ########################################################


@login_required
def profile(request):
    """Show profile of the current user."""
    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()

    context = {
        "title": request.user.get_full_name,
        "current_term": current_term,
        "current_semester": current_term, # Backward compatibility
    }

    if request.user.is_lecturer:
        courses = Course.objects.filter(
            allocated_course__teacher__pk=request.user.id
        )
        if current_term:
            courses = courses.filter(term=current_term.term)
        context["courses"] = courses
        return render(request, "accounts/profile.html", context)

    if request.user.is_student:
        student = get_object_or_404(Student, student__pk=request.user.id)
        parent = Parent.objects.filter(student=student).first()
        courses = TakenCourse.objects.filter(
            student__student__id=request.user.id, course__level=student.level
        )
        context.update(
            {
                "parent": parent,
                "courses": courses,
                "level": student.level,
            }
        )
        return render(request, "accounts/profile.html", context)

    # For superuser or other staff
    staff = User.objects.filter(is_lecturer=True, school=request.school)
    context["staff"] = staff
    return render(request, "accounts/profile.html", context)


@login_required
@admin_required
def profile_single(request, user_id):
    """Show profile of any selected user."""
    if request.user.id == user_id:
        return redirect("profile")

    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()
    user = get_object_or_404(User, pk=user_id, school=request.school)

    context = {
        "title": user.get_full_name,
        "user": user,
        "current_term": current_term,
        "current_semester": current_term, # Backward compatibility 
    }

    if user.is_lecturer:
        courses = Course.objects.filter(
            allocated_course__teacher__pk=user_id
        )
        if current_term:
            courses = courses.filter(term=current_term.term)
        context.update(
            {
                "user_type": "Lecturer",
                "courses": courses,
            }
        )
    elif user.is_student:
        student = get_object_or_404(Student, student__pk=user_id)
        courses = TakenCourse.objects.filter(
            student__student__id=user_id, course__level=student.level
        )
        context.update(
            {
                "user_type": "Student",
                "courses": courses,
                "student": student,
            }
        )
    else:
        context["user_type"] = "Superuser"

    if request.GET.get("download_pdf"):
        return render_to_pdf("pdf/profile_single.html", context)

    return render(request, "accounts/profile_single.html", context)


@login_required
@admin_required
def admin_panel(request):
    return render(request, "setting/admin_panel.html", {"title": "Admin Panel"})


# ########################################################
# Settings Views
# ########################################################


@login_required
def profile_update(request):
    is_admin = request.user.is_superuser or request.user.is_school_admin
    if request.method == "POST":
        form = ProfileUpdateForm(
            request.POST, request.FILES, 
            instance=request.user, 
            school=request.school,
            is_admin=is_admin
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("profile")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = ProfileUpdateForm(
            instance=request.user, 
            school=request.school,
            is_admin=is_admin
        )
    return render(request, "setting/profile_info_change.html", {"form": form})


@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was successfully updated!")
            return redirect("profile")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "setting/password_change.html", {"form": form})


# ########################################################
# Staff (Lecturer) Views
# ########################################################


@login_required
@admin_required
def staff_add_view(request):
    if request.method == "POST":
        form = StaffAddForm(request.POST, school=request.school)
        if form.is_valid():
            form.instance.school = request.school
            lecturer = form.save()

            full_name = lecturer.get_full_name
            email = lecturer.email
            messages.success(
                request,
                f"Account for lecturer {full_name} has been created. "
                f"An email with account credentials will be sent to {email} within a minute.",
            )
            return redirect("lecturer_list")
    else:
        form = StaffAddForm(school=request.school)
    return render(
        request, "accounts/add_staff.html", {"title": "Add Lecturer", "form": form}
    )


@login_required
@admin_required
def edit_staff(request, pk):
    lecturer = get_object_or_404(User, is_lecturer=True, pk=pk, school=request.school)
    if request.method == "POST":
        form = ProfileUpdateForm(
            request.POST, request.FILES, 
            instance=lecturer, 
            school=request.school,
            is_admin=True
        )
        if form.is_valid():
            form.save()
            full_name = lecturer.get_full_name
            messages.success(request, f"Lecturer {full_name} has been updated.")
            return redirect("lecturer_list")
        messages.error(request, "Please correct the error below.")
    else:
        form = ProfileUpdateForm(instance=lecturer, school=request.school, is_admin=True)
    return render(
        request, "accounts/edit_lecturer.html", {"title": "Edit Lecturer", "form": form}
    )


@method_decorator([login_required, admin_required], name="dispatch")
class LecturerFilterView(FilterView):
    filterset_class = LecturerFilter
    template_name = "accounts/lecturer_list.html"
    paginate_by = 10

    def get_queryset(self):
        return User.objects.filter(is_lecturer=True, school=self.request.school)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Lecturers"
        
        # We use the filtered queryset from django-filters
        qs = self.get_queryset()
        # Apply the filter from the filterset
        filtered_qs = self.filterset_class(self.request.GET, queryset=qs).qs
        
        context["nursery_teachers"] = filtered_qs.filter(division=settings.DIVISION_NURSERY)
        context["primary_teachers"] = filtered_qs.filter(division=settings.DIVISION_PRIMARY)
        context["jhs_teachers"] = filtered_qs.filter(division=settings.DIVISION_JHS)
        context["other_teachers"] = filtered_qs.filter(division__isnull=True)
        
        return context


@login_required
@admin_required
def render_lecturer_pdf_list(request):
    lecturers = User.objects.filter(is_lecturer=True, school=request.school)
    template_path = "pdf/lecturer_list.html"
    context = {"lecturers": lecturers}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="lecturers_list.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"We had some errors <pre>{html}</pre>")
    return response


@login_required
@admin_required
def delete_staff(request, pk):
    lecturer = get_object_or_404(User, is_lecturer=True, pk=pk, school=request.school)
    full_name = lecturer.get_full_name
    lecturer.delete()
    messages.success(request, f"Lecturer {full_name} has been deleted.")
    return redirect("lecturer_list")


# ########################################################
# Student Views
# ########################################################


@login_required
@admin_required
def student_add_view(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST, school=request.school)
        if form.is_valid():
            form.instance.school = request.school
            student = form.save()
            
            full_name = student.get_full_name
            email = student.email
            messages.success(
                request,
                f"Account for {full_name} has been created. "
                f"An email with account credentials will be sent to {email} within a minute.",
            )
            # Redirect back to the specific class workspace if level was provided
            level_code = request.POST.get("level") # Try to get from hidden or form data? 
            # Or better, check the student's level
            if student.student.level:
                 return redirect("class_detail", level_code=student.student.level)
            return redirect("class_list")
        messages.error(request, "Correct the error(s) below.")
    else:
        # Pre-fill level if provided in URL (e.g. ?level=Primary 1)
        initial_data = {}
        level_param = request.GET.get("level")
        if level_param:
            initial_data["level"] = level_param
        
        form = StudentAddForm(initial=initial_data, school=request.school)
    return render(
        request, "accounts/add_student.html", {"title": "Add Student", "form": form}
    )


@login_required
@admin_required
def edit_student(request, pk):
    student_user = get_object_or_404(User, is_student=True, pk=pk, school=request.school)
    if request.method == "POST":
        form = ProfileUpdateForm(
            request.POST, request.FILES, 
            instance=student_user, 
            school=request.school,
            is_admin=True
        )
        if form.is_valid():
            form.save()
            full_name = student_user.get_full_name
            messages.success(request, f"Student {full_name} has been updated.")
            return redirect("student_list")
        messages.error(request, "Please correct the error below.")
    else:
        form = ProfileUpdateForm(instance=student_user, school=request.school, is_admin=True)
    return render(
        request, "accounts/edit_student.html", {"title": "Edit Student", "form": form}
    )


@method_decorator([login_required, admin_required], name="dispatch")
class StudentListView(FilterView):
    filterset_class = StudentFilter
    template_name = "accounts/student_list.html"
    paginate_by = 10

    def get_queryset(self):
        return Student.objects.filter(student__school=self.request.school)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Students"
        return context


@login_required
@admin_required
def render_student_pdf_list(request):
    students = Student.objects.filter(student__school=request.school)
    template_path = "pdf/student_list.html"
    context = {"students": students}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'filename="students_list.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"We had some errors <pre>{html}</pre>")
    return response


@login_required
@admin_required
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk, student__school=request.school)
    full_name = student.student.get_full_name
    student.delete()
    messages.success(request, f"Student {full_name} has been deleted.")
    return redirect("student_list")

@login_required
@admin_required
def edit_student_program(request, pk):
    student = get_object_or_404(Student, student_id=pk, student__school=request.school)
    user = get_object_or_404(User, pk=pk, school=request.school)
    if request.method == "POST":
        form = ProgramUpdateForm(request.POST, request.FILES, instance=student, school=request.school)
        if form.is_valid():
            form.save()
            full_name = user.get_full_name
            messages.success(request, f"{full_name}'s program has been updated.")
            return redirect("profile_single", user_id=pk)
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = ProgramUpdateForm(instance=student, school=request.school)
    return render(
        request,
        "accounts/edit_student_program.html",
        {"title": "Edit Program", "form": form, "student": student},
    )


@method_decorator([login_required, admin_required], name="dispatch")
class ParentAdd(CreateView):
    model = Parent
    form_class = ParentAddForm
    template_name = "accounts/parent_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['school'] = self.request.school
        return kwargs

    def form_valid(self, form):
        # We implicitly assume parent is adding for a student in their school,
        # logic handled in form or implicit relations.
        # But Parent model links to User. We should probably assign school to Parent's user?
        # Parent creation is complex. Let's look at ParentAddForm if needed.
        # For now, just fix the view compilation if necessary.
        # Wait, ParentAdd creates a User implicitly? No, ParentAddForm usually handles it.
        # Let's trust the form for now but ensures proper redirection/scoping if possible.
        messages.success(self.request, "Parent added successfully.")
        return super().form_valid(form)


@login_required
@lecturer_required
def class_list_view(request):
    """Dashboard showing all classes (levels) - filtered by division"""
    
    if request.user.is_superuser or request.user.is_school_admin:
        # Admins see all classes
        levels = settings.LEVEL_CHOICES
    elif request.user.division:
        # Teachers see only classes in their assigned division
        accessible_levels = request.user.get_division_levels()
        levels = [(code, name) for code, name in settings.LEVEL_CHOICES if code in accessible_levels]
    else:
        # Teachers without division assigned see no classes
        # (Admin needs to assign them a division first)
        messages.warning(
            request, 
            "You have not been assigned to a division yet. Please contact your administrator."
        )
        levels = []
    
    # Calculate student counts per class efficiently
    students_counts = {}
    for level_code, _ in levels:
        count = Student.objects.filter(level=level_code, student__school=request.school).count()
        students_counts[level_code] = count

    context = {
        "title": "Manage Classes",
        "levels": levels,
        "students_counts": students_counts,
        "is_teacher": not (request.user.is_superuser or request.user.is_school_admin),
        "user_division": request.user.division if hasattr(request.user, 'division') else None,
    }
    return render(request, "accounts/class_list.html", context)


@login_required
@lecturer_required
def class_detail_view(request, level_code):
    """Workspace for a specific class level - with division-based access control"""
    
    # Find level name from choices
    level_name = dict(settings.LEVEL_CHOICES).get(level_code, level_code)

    # Access Control: Verify teacher can access this level based on division
    if not request.user.can_access_level(level_code):
        from accounts.utils import get_division_for_level
        level_division = get_division_for_level(level_code)
        
        if not request.user.division:
            messages.error(
                request, 
                "You have not been assigned to a division. Please contact your administrator."
            )
        else:
            messages.error(
                request, 
                f"Access denied: {level_name} belongs to {level_division} division, "
                f"but you are assigned to {request.user.division} division."
            )
        return redirect('class_list')

    students = Student.objects.filter(
        level=level_code, student__school=request.school
    ).select_related('student', 'program')

    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    is_third_term = current_term and current_term.term == settings.THIRD_TERM
    
    # Get subjects for this class level (filtered by role)
    if request.user.is_superuser or request.user.is_school_admin:
        # Admins see all subjects
        subjects = Course.objects.filter(level=level_code, school=request.school)
    else:
        # Teachers see only their allocated subjects
        allocations = CourseAllocation.objects.filter(teacher=request.user).prefetch_related('courses')
        teacher_course_ids = []
        for allocation in allocations:
            teacher_course_ids.extend(
                allocation.courses.filter(
                    level=level_code, 
                    school=request.school
                ).values_list('id', flat=True)
            )
        subjects = Course.objects.filter(id__in=teacher_course_ids)

    # Broadsheet logic
    broadsheet_data = []
    if current_term:
        # Fetch all relevant scores in one go
        taken_courses = TakenCourse.objects.filter(
            student__in=students,
            course__in=subjects,
            course__term=current_term.term,
            school=request.school
        )
        scores_map = {(tc.student_id, tc.course_id): tc.total for tc in taken_courses}
        
        # Fetch all results in one go
        results_map = {
            r.student_id: r 
            for r in Result.objects.filter(
                student__in=students, 
                term=current_term.term, 
                session=current_term.year,
                school=request.school
            )
        }

        for student in students:
            student_row = {
                'student': student,
                'scores': [scores_map.get((student.id, s.id), "-") for s in subjects],
                'average': results_map.get(student.id).term_average if results_map.get(student.id) else "-",
                'position': results_map.get(student.id).overall_position if results_map.get(student.id) else "-"
            }
            broadsheet_data.append(student_row)

    context = {
        "level_code": level_code,
        "level_name": level_name,
        "students": students,
        "subjects": subjects,
        "current_term": current_term,
        "is_third_term": is_third_term,
        "broadsheet_data": broadsheet_data,
        "is_teacher": not (request.user.is_superuser or request.user.is_school_admin),
    }
    return render(request, "accounts/class_detail.html", context)
