from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.template.loader import get_template, render_to_string
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import CreateView
from django_filters.views import FilterView
from xhtml2pdf import pisa
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from io import BytesIO
from datetime import date, datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from docx import Document

from accounts.decorators import admin_required, lecturer_required
from accounts.filters import LecturerFilter, StudentFilter
from accounts.forms import (
    ParentAddForm,
    ProfileUpdateForm,
    ProgramUpdateForm,
    NonTeachingStaffAddForm,
    StaffAddForm,
    StaffPromotionForm,
    StudentAddForm,
)
from accounts.models import Parent, PasswordResetAudit, Student, User, NON_TEACHING_POSITIONS
from school.forms import StudentIDFormatForm
from core.models import Semester
from course.models import Course, CourseAllocation, Program
from result.models import TakenCourse, Result

# ########################################################
# Utility Functions
# ########################################################


def render_to_pdf(template_name, context):
    """Render a given template to PDF format."""
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="profile.pdf"'
    template = render_to_string(template_name, context)
    pdf = pisa.CreatePDF(template, dest=response)
    if pdf.err:
        return HttpResponse("We had some problems generating the PDF")
    return response


def render_credential_handoff(request, user, temporary_password, back_url):
    """Display newly issued credentials once without caching the response."""
    response = render(
        request,
        "accounts/credential_handoff.html",
        {
            "user_account": user,
            "temporary_password": temporary_password,
            "back_url": back_url,
        },
    )
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


# ########################################################
# Authentication and Registration
# ########################################################


class RoleAwareLoginView(auth_views.LoginView):
    """Send super admins to the superadmin panel after the shared login."""

    def get_success_url(self):
        if self.request.user.must_change_password:
            return reverse("change_password")
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to

        if self.request.user.is_superuser:
            return reverse("superadmin:dashboard")

        if self.request.user.is_school_admin:
            return reverse("dashboard")

        try:
            return reverse("home")
        except NoReverseMatch:
            # The master domain does not mount the school app. The middleware
            # switches non-superusers to the public URLconf on the next
            # request, so send them to the shared root path.
            return "/"


def validate_username(request):
    username = request.GET.get("username", None)
    data = {"is_taken": User.objects.filter(username__iexact=username).exists()}
    return JsonResponse(data)


def register(request):
    if request.method == "POST":
        form = StudentAddForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            if form.temporary_password:
                return render_credential_handoff(
                    request, user, form.temporary_password, reverse("login")
                )
            messages.success(request, "Account created successfully. You can now sign in.")
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
        parent = Parent.objects.filter(student=student).select_related("user").first()
        courses = TakenCourse.objects.filter(
            student__student__id=user_id, course__level=student.level
        )
        context.update(
            {
                "user_type": "Student",
                "courses": courses,
                "student": student,
                "parent": parent,
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
    student_id_format_form = None
    student_id_next = {"Nursery": 1, "Primary": 1, "JHS": 1}
    if request.school:
        if request.method == "POST" and request.POST.get("action") == "save_student_id_formats":
            student_id_format_form = StudentIDFormatForm(
                request.POST, instance=request.school
            )
            if student_id_format_form.is_valid():
                student_id_format_form.save()
                messages.success(request, "Student ID formats saved.")
                return redirect("admin_panel")
            messages.error(request, "Please correct the student ID format errors below.")
        else:
            student_id_format_form = StudentIDFormatForm(instance=request.school)
        for sequence in request.school.student_id_sequences.all():
            student_id_next[sequence.division] = sequence.last_number + 1

    reset_events = PasswordResetAudit.objects.select_related("target_user", "performed_by")
    if not request.user.is_superuser:
        reset_events = reset_events.filter(school=request.school)
    return render(request, "setting/admin_panel.html", {
        "title": "Admin Panel",
        "password_reset_events": reset_events[:10],
        "student_id_format_form": student_id_format_form,
        "school_code": f"S{request.school.pk}" if request.school else "S1",
        "student_id_next": student_id_next,
    })


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
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was successfully updated!")
            return redirect("profile")
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "setting/password_change.html", {"form": form})


@login_required
@admin_required
@require_POST
def reset_user_password(request, user_id):
    users = User.objects.all() if request.user.is_superuser else User.objects.filter(school=request.school)
    user = get_object_or_404(users, pk=user_id)
    password = User.objects.make_random_password(length=16)
    user.set_password(password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    PasswordResetAudit.objects.create(
        target_user=user,
        performed_by=request.user,
        school=user.school,
        target_username=user.username,
        performed_by_username=request.user.username,
    )
    return render_credential_handoff(
        request, user, password, reverse("admin_panel")
    )


# ########################################################
# Teacher Views
# ########################################################


@login_required
@admin_required
def staff_add_view(request):
    if request.method == "POST":
        form = StaffAddForm(request.POST, request.FILES, school=request.school)
        if form.is_valid():
            form.instance.school = request.school
            lecturer = form.save()
            return render_credential_handoff(
                request,
                lecturer,
                form.temporary_password,
                reverse("lecturer_list"),
            )
    else:
        form = StaffAddForm(school=request.school)
    return render(
        request, "accounts/add_staff.html", {"title": "Add Teacher", "form": form}
    )


@login_required
@admin_required
def edit_staff(request, pk):
    lecturer = get_object_or_404(User, Q(is_lecturer=True) | Q(is_teacher=True), pk=pk, school=request.school)
    if request.GET.get("assignment") == "1":
        initial = {
            "division": lecturer.division or "",
            "assigned_level": lecturer.assigned_level or "",
            "is_class_teacher": lecturer.is_class_teacher,
        }
        assignment_form = StaffPromotionForm(
            request.POST or None, initial=initial, school=request.school
        )
        if request.method == "POST" and assignment_form.is_valid():
            division = assignment_form.cleaned_data["division"]
            department, _ = Program.objects.get_or_create(
                school=request.school,
                division=division,
                is_academic_block=True,
                defaults={"title": dict(settings.DIVISION_CHOICES).get(division)},
            )
            lecturer.division = division
            lecturer.department = department
            lecturer.assigned_level = assignment_form.cleaned_data.get("assigned_level") or None
            lecturer.is_class_teacher = assignment_form.cleaned_data.get("is_class_teacher", False)
            lecturer.save(update_fields=["division", "department", "assigned_level", "is_class_teacher"])
            messages.success(request, f"{lecturer.get_full_name}'s teaching assignment has been updated.")
            return redirect("lecturer_list")
        return render(request, "accounts/staff_assignment.html", {
            "title": "Change Teaching Division or Class",
            "staff_member": lecturer,
            "form": assignment_form,
        })
    if request.method == "POST":
        form = ProfileUpdateForm(
            request.POST, request.FILES, 
            instance=lecturer, 
            school=request.school,
            is_admin=True,
            is_staff_admin=True,
        )
        if form.is_valid():
            form.save()
            full_name = lecturer.get_full_name
            messages.success(request, f"Teacher {full_name} has been updated.")
            return redirect("lecturer_list")
        messages.error(request, "Please correct the error below.")
    else:
        form = ProfileUpdateForm(
            instance=lecturer,
            school=request.school,
            is_admin=True,
            is_staff_admin=True,
        )
    return render(
        request, "accounts/edit_lecturer.html", {"title": "Edit Teacher", "form": form}
    )


@method_decorator([login_required, admin_required], name="dispatch")
class LecturerFilterView(FilterView):
    filterset_class = LecturerFilter
    template_name = "accounts/lecturer_list.html"
    paginate_by = 10

    def get_queryset(self):
        return User.objects.filter(Q(is_lecturer=True) | Q(is_teacher=True), school=self.request.school).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Teachers"
        
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
def non_teaching_staff_list(request):
    staff = User.objects.filter(
        school=request.school,
        is_non_teaching_staff=True,
    ).order_by("first_name", "last_name", "username")
    query = request.GET.get("q", "").strip()
    if query:
        staff = staff.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
            | Q(non_teaching_position__icontains=query)
        )
    return render(request, "accounts/non_teaching_staff_list.html", {
        "title": "Non-teaching Staff",
        "staff_members": staff,
        "search_query": query,
    })


@login_required
@admin_required
def non_teaching_staff_add(request):
    form = NonTeachingStaffAddForm(
        request.POST or None,
        request.FILES or None,
        school=request.school,
    )
    if request.method == "POST" and form.is_valid():
        staff_member = form.save()
        return render_credential_handoff(
            request,
            staff_member,
            form.temporary_password,
            reverse("non_teaching_staff_list"),
        )
    return render(request, "accounts/non_teaching_staff_form.html", {
        "title": "Add Non-teaching Staff",
        "form": form,
        "is_edit": False,
    })


@login_required
@admin_required
def non_teaching_staff_edit(request, pk):
    staff_member = get_object_or_404(
        User,
        pk=pk,
        school=request.school,
        is_non_teaching_staff=True,
    )
    form = ProfileUpdateForm(
        request.POST or None,
        request.FILES or None,
        instance=staff_member,
        school=request.school,
        is_admin=True,
        is_staff_admin=False,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{staff_member.get_full_name} has been updated.")
        return redirect("non_teaching_staff_list")
    return render(request, "accounts/non_teaching_staff_form.html", {
        "title": "Edit Non-teaching Staff",
        "form": form,
        "is_edit": True,
        "staff_member": staff_member,
    })


@login_required
@admin_required
@require_POST
def non_teaching_staff_delete(request, pk):
    staff_member = get_object_or_404(
        User,
        pk=pk,
        school=request.school,
        is_non_teaching_staff=True,
    )
    name = staff_member.get_full_name
    staff_member.delete()
    messages.success(request, f"{name} has been removed from non-teaching staff.")
    return redirect("non_teaching_staff_list")


@login_required
@admin_required
def promote_non_teaching_staff(request, pk):
    staff_member = get_object_or_404(
        User, pk=pk, school=request.school, is_non_teaching_staff=True
    )
    form = StaffPromotionForm(request.POST or None, school=request.school)
    if request.method == "POST" and form.is_valid():
        division = form.cleaned_data["division"]
        department_title = dict(settings.DIVISION_CHOICES).get(division)
        department, _ = Program.objects.get_or_create(
            school=request.school, division=division, is_academic_block=True,
            defaults={"title": department_title},
        )
        staff_member.is_non_teaching_staff = False
        staff_member.non_teaching_position = ""
        staff_member.is_teacher = True
        staff_member.is_lecturer = True
        staff_member.division = division
        staff_member.assigned_level = form.cleaned_data.get("assigned_level") or None
        staff_member.department = department
        staff_member.is_class_teacher = form.cleaned_data.get("is_class_teacher", False)
        staff_member.save()
        messages.success(request, f"{staff_member.get_full_name} is now registered as a teacher.")
        return redirect("lecturer_list")
    return render(request, "accounts/promote_staff.html", {
        "title": "Promote to Teacher", "staff_member": staff_member, "form": form,
    })


def _staff_queryset(request, staff_type):
    if staff_type == "teachers":
        return User.objects.filter(school=request.school).filter(
            Q(is_teacher=True) | Q(is_lecturer=True)
        ).distinct().order_by("last_name", "first_name", "username")
    return User.objects.filter(
        school=request.school, is_non_teaching_staff=True
    ).order_by("last_name", "first_name", "username")


STAFF_EXPORT_COLUMNS = (
    ("Staff type", "staff_type"),
    ("Username", "username"), ("First name", "first_name"),
    ("Other names", "other_names"), ("Last name", "last_name"),
    ("Gender", "gender"), ("Date of birth", "date_of_birth"),
    ("Place of birth", "place_of_birth"), ("Nationality", "nationality"),
    ("Hometown", "hometown"), ("Region", "region"), ("District", "district"),
    ("Religion", "religion"), ("Marital status", "marital_status"),
    ("Ghana Card number", "ghana_card_number"), ("NHIS number", "nhis_number"),
    ("GhanaPost GPS address", "gps_address"), ("Phone", "phone"),
    ("Alternate phone", "alternate_phone"), ("Email", "email"),
    ("Residential address", "address"), ("GES staff ID", "staff_id"),
    ("SSNIT number", "ssnit_number"), ("TIN number", "tin_number"),
    ("Payroll number", "payroll_number"),
    ("National service number", "national_service_number"),
    ("First appointment date", "date_of_first_appointment"),
    ("Current appointment date", "date_of_current_appointment"),
    ("Employment date", "date_employed"), ("Employment type", "employment_type"),
    ("Designation / rank", "designation"), ("Work unit", "work_unit"),
    ("Highest qualification", "highest_qualification"),
    ("Qualification institution", "qualification_institution"),
    ("Qualification year", "qualification_year"),
    ("Professional qualification", "professional_qualification"),
    ("Subject specialization", "subject_specialization"),
    ("NTC license number", "ntc_license_number"),
    ("NTC license expiry", "ntc_license_expiry"),
    ("Bank name", "bank_name"), ("Bank branch", "bank_branch"),
    ("Bank account name", "bank_account_name"),
    ("Bank account number", "bank_account_number"),
    ("Emergency contact name", "emergency_contact_name"),
    ("Emergency contact relationship", "emergency_contact_relationship"),
    ("Emergency contact phone", "emergency_contact_phone"),
    ("Emergency contact address", "emergency_contact_address"),
    ("Division", "division"), ("Assigned class", "assigned_level"),
    ("Class teacher", "is_class_teacher"),
    ("Non-teaching position", "non_teaching_position"),
)

STAFF_IMPORT_FIELDS = tuple(
    field for _, field in STAFF_EXPORT_COLUMNS
    if field not in {"staff_type", "username"}
)
IMPORT_COLUMNS = ["staff_type", "username"] + list(dict.fromkeys(STAFF_IMPORT_FIELDS))
REQUIRED_IMPORT_COLUMNS = {"staff_type", "first_name", "last_name"}


def _staff_export_value(person, field):
    if field == "staff_type":
        return "Teacher" if person.is_teacher or person.is_lecturer else "Non-teaching"
    if field == "is_class_teacher":
        return "Yes" if person.is_class_teacher else "No"
    model_field = User._meta.get_field(field)
    value = getattr(person, field, "")
    if value in (None, ""):
        return ""
    if model_field.choices:
        return getattr(person, f"get_{field}_display")()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _clean_staff_import_value(field_name, value):
    model_field = User._meta.get_field(field_name)
    if model_field.get_internal_type() == "BooleanField" and value in (None, ""):
        return False
    if field_name == "is_class_teacher":
        normalized = str(value).strip().casefold()
        if normalized in {"yes", "y", "true", "1", "on"}:
            return True
        if normalized in {"no", "n", "false", "0", "off"}:
            return False
        raise ValueError("use Yes or No")
    if value in (None, ""):
        return None if model_field.null else ""
    if model_field.choices:
        candidate = str(value).strip()
        choice_values = {str(key) for key, _ in model_field.flatchoices}
        by_label = {str(label).casefold(): key for key, label in model_field.flatchoices}
        if candidate in choice_values:
            value = candidate
        elif candidate.casefold() in by_label:
            value = by_label[candidate.casefold()]
        else:
            raise ValueError("choose one of the listed values")
    return model_field.clean(value, None)


@login_required
@admin_required
def export_staff(request, staff_type, file_type):
    if staff_type not in {"teachers", "non-teaching"} or file_type not in {"xlsx", "docx"}:
        return HttpResponse(status=404)
    staff = _staff_queryset(request, staff_type)
    title = "Teachers" if staff_type == "teachers" else "Non-teaching Staff"
    if file_type == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title[:31]
        sheet.append([heading for heading, _ in STAFF_EXPORT_COLUMNS])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24476B")
        for person in staff:
            sheet.append([_staff_export_value(person, field) for _, field in STAFF_EXPORT_COLUMNS])
        for column_cells in sheet.columns:
            values = [len(str(cell.value or "")) for cell in column_cells[:100]]
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max(values, default=10) + 2, 12), 32)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        output = BytesIO()
        workbook.save(output)
        response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{staff_type}_staff.xlsx"'
        return response
    document = Document()
    document.add_heading(title, 0)
    for index, person in enumerate(staff, start=1):
        document.add_heading(f"{index}. {person.get_full_name}", level=1)
        table = document.add_table(rows=0, cols=2)
        table.style = "Light Shading Accent 1"
        for heading, field in STAFF_EXPORT_COLUMNS:
            if field == "staff_id" and heading == "Staff ID":
                continue
            cells = table.add_row().cells
            cells[0].text = heading
            cells[1].text = str(_staff_export_value(person, field))
    output = BytesIO()
    document.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    response["Content-Disposition"] = f'attachment; filename="{staff_type}_staff.docx"'
    return response


@login_required
@admin_required
def import_staff(request):
    errors = []
    imported = 0
    if request.method == "POST" and request.FILES.get("workbook"):
        try:
            workbook = load_workbook(request.FILES["workbook"], read_only=True, data_only=True)
            sheet = workbook.active
            rows = sheet.iter_rows(values_only=True)
            headers = [str(value or "").strip().lower() for value in next(rows, ())]
            missing = REQUIRED_IMPORT_COLUMNS - set(headers)
            if missing:
                errors.append("Missing required columns: " + ", ".join(sorted(missing)))
            else:
                positions = {name: headers.index(name) for name in IMPORT_COLUMNS if name in headers}
                data = []
                seen_usernames = set()
                for row_number, row in enumerate(rows, start=2):
                    values = {name: (row[index] if index < len(row) else None) for name, index in positions.items()}
                    values.setdefault("username", None)
                    for optional_field in STAFF_IMPORT_FIELDS:
                        values.setdefault(optional_field, None)
                    if not any(value not in (None, "") for value in values.values()):
                        continue
                    for phone_field in ("phone", "alternate_phone", "emergency_contact_phone"):
                        raw_phone = values.get(phone_field)
                        if isinstance(raw_phone, (int, float)) and str(int(raw_phone)).isdigit() and len(str(int(raw_phone))) == 9:
                            values[phone_field] = f"0{int(raw_phone)}"
                    values = {
                        name: value.date().isoformat() if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else str(value).strip() if value is not None else ""
                        for name, value in values.items()
                    }
                    values["staff_type"] = values["staff_type"].strip().casefold()
                    if not values["first_name"] or not values["last_name"]:
                        errors.append(f"Row {row_number}: first_name and last_name are required.")
                    elif values["staff_type"].lower() not in {"teacher", "non-teaching"}:
                        errors.append(f"Row {row_number}: staff_type must be teacher or non-teaching.")
                    elif values["staff_type"] == "teacher" and not values["division"]:
                        errors.append(f"Row {row_number}: provide a valid division for this teacher.")
                    elif values["username"] and User.objects.filter(username__iexact=values["username"]).exists():
                        errors.append(f"Row {row_number}: username {values['username']} already exists.")
                    elif values["username"] and values["username"].casefold() in seen_usernames:
                        errors.append(f"Row {row_number}: username {values['username']} is repeated in this workbook.")
                    else:
                        cleaned_values = {"staff_type": values["staff_type"], "username": values["username"]}
                        for field_name in STAFF_IMPORT_FIELDS:
                            try:
                                cleaned_values[field_name] = _clean_staff_import_value(field_name, values[field_name])
                            except Exception as exc:
                                errors.append(f"Row {row_number}: {field_name}: {exc}")
                        division = cleaned_values.get("division")
                        level = cleaned_values.get("assigned_level")
                        if division and division not in dict(settings.DIVISION_CHOICES):
                            errors.append(f"Row {row_number}: choose a valid division.")
                        elif level and level not in settings.DIVISION_LEVEL_MAPPING.get(division, []):
                            errors.append(f"Row {row_number}: assigned_level does not belong to division.")
                        elif cleaned_values["staff_type"] == "non-teaching" and not cleaned_values.get("non_teaching_position"):
                            errors.append(f"Row {row_number}: choose a non-teaching position.")
                        elif cleaned_values["staff_type"] == "non-teaching" and cleaned_values.get("is_class_teacher"):
                            errors.append(f"Row {row_number}: non-teaching staff cannot be class teachers.")
                        if not any(error.startswith(f"Row {row_number}:") for error in errors):
                            cleaned_values["row_number"] = row_number
                            if values["username"]:
                                seen_usernames.add(values["username"].casefold())
                            data.append(cleaned_values)
                if not errors:
                    with transaction.atomic():
                        for values in data:
                            is_teacher = values["staff_type"].lower() == "teacher"
                            username = values["username"] or f"staff{timezone.now().strftime('%y%m%d%H%M%S%f')}{values['row_number']}"
                            user = User.objects.create_user(
                                username=username,
                                password=User.objects.make_random_password(length=16),
                                school=request.school,
                                first_name=values["first_name"], last_name=values["last_name"],
                                is_teacher=is_teacher, is_lecturer=is_teacher,
                                is_non_teaching_staff=not is_teacher,
                                must_change_password=True,
                            )
                            for field_name in STAFF_IMPORT_FIELDS:
                                setattr(user, field_name, values.get(field_name))
                            if is_teacher:
                                user.non_teaching_position = ""
                            else:
                                user.is_class_teacher = False
                            if is_teacher:
                                title = dict(settings.DIVISION_CHOICES)[values["division"]]
                                user.department, _ = Program.objects.get_or_create(
                                    school=request.school, division=values["division"], is_academic_block=True,
                                    defaults={"title": title},
                                )
                            user.save()
                            imported += 1
                    messages.success(request, f"Imported {imported} staff account(s). Temporary passwords must be reset by an administrator before first sign-in.")
                    return redirect("non_teaching_staff_list")
        except Exception as exc:
            errors.append(f"Could not read this Excel workbook: {exc}")
    return render(request, "accounts/import_staff.html", {
        "title": "Import staff from Excel", "errors": errors,
        "import_columns": IMPORT_COLUMNS,
    })


@login_required
@admin_required
def download_staff_import_template(request):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Staff import"
    sheet.append(IMPORT_COLUMNS)
    teacher_example = {
        "staff_type": "teacher", "first_name": "Ama", "last_name": "Mensah",
        "gender": "F", "phone": "0200000000", "division": "Primary",
        "assigned_level": "Primary 1", "designation": "Teacher",
        "work_unit": "Primary", "employment_type": "PERMANENT",
        "is_class_teacher": "No",
    }
    non_teacher_example = {
        "staff_type": "non-teaching", "first_name": "Kofi", "last_name": "Owusu",
        "gender": "M", "phone": "0200000001", "designation": "Cleaner",
        "work_unit": "Operations", "employment_type": "PERMANENT",
        "non_teaching_position": "CLEANER",
    }
    for example in (teacher_example, non_teacher_example):
        sheet.append([example.get(column, "") for column in IMPORT_COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DCEAF7")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for field_name in {
        "phone", "alternate_phone", "emergency_contact_phone", "ghana_card_number",
        "nhis_number", "staff_id", "ssnit_number", "tin_number", "payroll_number",
        "national_service_number", "ntc_license_number", "bank_account_number",
    }:
        if field_name in IMPORT_COLUMNS:
            column_index = IMPORT_COLUMNS.index(field_name) + 1
            for row_index in range(2, sheet.max_row + 1):
                sheet.cell(row=row_index, column=column_index).number_format = "@"
    sheet.column_dimensions["A"].width = 18
    for column_cells in sheet.columns:
        sheet.column_dimensions[column_cells[0].column_letter].width = max(
            min(max(len(str(cell.value or "")) for cell in column_cells[:3]) + 2, 28),
            sheet.column_dimensions[column_cells[0].column_letter].width or 10,
        )
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="staff_import_template.xlsx"'
    return response


@login_required
@admin_required
def render_lecturer_pdf_list(request):
    lecturers = User.objects.filter(Q(is_lecturer=True) | Q(is_teacher=True), school=request.school).distinct()
    template_path = "pdf/lecturer_list.html"
    context = {"lecturers": lecturers}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="teachers_list.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse(f"We had some errors <pre>{html}</pre>")
    return response


@login_required
@admin_required
def delete_staff(request, pk):
    lecturer = get_object_or_404(User, Q(is_lecturer=True) | Q(is_teacher=True), pk=pk, school=request.school)
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
        form = StudentAddForm(request.POST, request.FILES, school=request.school)
        if form.is_valid():
            form.instance.school = request.school
            student = form.save()
            back_url = (
                reverse("class_detail", kwargs={"level_code": student.student.level})
                if student.student.level
                else reverse("class_list")
            )
            return render_credential_handoff(
                request, student, form.temporary_password, back_url
            )
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
        return Student.objects.filter(student__school=self.request.school).select_related("student", "program")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Students"

        qs = self.get_queryset()
        filtered_qs = self.filterset_class(self.request.GET, queryset=qs).qs

        context["nursery_students"] = filtered_qs.filter(student__division=settings.DIVISION_NURSERY)
        context["primary_students"] = filtered_qs.filter(student__division=settings.DIVISION_PRIMARY)
        context["jhs_students"] = filtered_qs.filter(student__division=settings.DIVISION_JHS)
        context["other_students"] = filtered_qs.filter(student__division__isnull=True)

        return context


@login_required
@admin_required
def render_student_pdf_list(request):
    students = Student.objects.filter(student__school=request.school)
    template_path = "pdf/student_list.html"
    context = {"students": students}
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="students_list.pdf"'
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

    def get_success_url(self):
        return reverse(
            "profile_single", kwargs={"user_id": self.object.user_id}
        )

    def form_valid(self, form):
        parent = form.save()
        self.object = parent
        messages.success(self.request, "Parent added successfully.")
        return render_credential_handoff(
            self.request,
            parent.user,
            form.temporary_password,
            reverse("profile_single", kwargs={"user_id": parent.user_id}),
        )


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
