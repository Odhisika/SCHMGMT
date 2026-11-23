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
from django.db.models import Q, Count, Max
from django.db import transaction
from django.utils import timezone
from io import BytesIO
from datetime import date, datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from docx import Document
from core.pdf_utils import get_school_document_frame, clean_hex_color
from core.search import build_search_query

from accounts.decorators import admin_required, lecturer_required, school_admin_required
from accounts.filters import LecturerFilter, StudentFilter
from accounts.forms import (
    BulkSubClassForm,
    ParentAddForm,
    ProfileUpdateForm,
    ProgramUpdateForm,
    NonTeachingStaffAddForm,
    SchoolAdminAddForm,
    StaffAddForm,
    StaffPromotionForm,
    StudentAddForm,
    StudentTransferForm,
    SubClassForm,
)
from accounts.models import (
    ClassTransfer,
    NON_TEACHING_POSITIONS,
    Parent,
    PasswordResetAudit,
    STUDENT_STATUS_ACTIVE,
    Student,
    SubClass,
    User,
)
from accounts.utils import generate_student_credentials, get_division_for_level
from school.division_utils import (
    get_division_choices,
    get_division_labels,
    get_level_choices,
    get_levels_for_division,
    is_known_division,
)
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
    try:
        login_url = request.build_absolute_uri(reverse("login"))
    except Exception:
        login_url = "/accounts/login/"
    school = getattr(request, "school", None) or getattr(user, "school", None)
    frame_path = get_school_document_frame(school)
    primary_color = clean_hex_color(getattr(school, "primary_color", None), "#0c2340")
    secondary_color = clean_hex_color(getattr(school, "secondary_color", None), "#7cb342")
    accent_color = clean_hex_color(getattr(school, "accent_color", None), "#f59e0b")

    response = render(
        request,
        "accounts/credential_handoff.html",
        {
            "user_account": user,
            "temporary_password": temporary_password,
            "back_url": back_url,
            "login_url": login_url,
            "school": school,
            "background_image_path": frame_path,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "accent_color": accent_color,
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

    # If an already-authenticated user lands on the login page (for example by
    # pressing the browser Back button after signing in), send them back into
    # the app instead of showing the login form again.
    redirect_authenticated_user = True

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


class AppLogoutView(auth_views.LogoutView):
    """Sign out, destroy the session and never allow the page to be restored."""

    # Keep GET working for the existing sign-out links (including HTMX pages);
    # POST is also accepted and is what new forms should use.
    http_method_names = ["get", "head", "post", "options"]

    def get_default_redirect_url(self):
        return reverse("login")

    def get(self, request, *args, **kwargs):
        # LogoutView only logs out on POST. Existing templates use GET links,
        # so make GET perform the same logout-and-redirect flow.
        return self.post(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if not response.has_header("Cache-Control") or "no-store" not in response["Cache-Control"]:
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        # Also ask supporting browsers to drop any cache left over from before
        # this fix (HTTPS only; silently ignored on plain HTTP).
        response["Clear-Site-Data"] = '"cache"'
        # Drop the now-invalid session cookie from the browser as well.
        response.delete_cookie(
            settings.SESSION_COOKIE_NAME,
            path=settings.SESSION_COOKIE_PATH,
            domain=settings.SESSION_COOKIE_DOMAIN,
            samesite=settings.SESSION_COOKIE_SAMESITE,
        )
        return response


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
        level = request.GET.get("level") or None
        session = request.GET.get("session") or None
        term = request.GET.get("term") or None
        context.update(
            {
                "parent": parent,
                "courses": courses,
                "level": student.level,
                "student": student,
            }
        )
        context.update(_build_student_history_context(student, request.school, level=level, session=session, term=term))
        return render(request, "accounts/profile.html", context)

    # For superuser or other staff
    staff = User.objects.filter(is_lecturer=True, school=request.school)
    context["staff"] = staff
    return render(request, "accounts/profile.html", context)


def _build_student_history_context(student, school, level=None, session=None, term=None):
    from django.db.models import Sum
    from attendance.models import Attendance, AttendanceSummary
    from fees.models import StudentFeeAssignment, Payment
    from result.models import PromotionDecision

    results_qs = Result.objects.filter(student=student, school=school)
    taken_qs = TakenCourse.objects.select_related("course").filter(student=student, school=school)
    attendance_qs = Attendance.objects.filter(student=student, school=school)
    attendance_summary_qs = AttendanceSummary.objects.select_related("term").filter(student=student, school=school)
    fees_qs = StudentFeeAssignment.objects.select_related("fee_structure", "term").filter(student=student)
    payments_qs = Payment.objects.select_related("assignment", "assignment__fee_structure", "assignment__term").filter(student=student, school=school)
    decisions_qs = PromotionDecision.objects.filter(student=student, school=school)

    # Determine admission/graduation window
    admission_date = getattr(student, "admission_date", None) or student.student.date_joined.date()
    all_sessions = sorted({s for s in results_qs.values_list("session", flat=True) if s} |
                          {s for s in decisions_qs.values_list("session", flat=True) if s})
    # include fee/payment/attendance years if present
    for d in fees_qs.values_list("term__year", flat=True):
        if d: all_sessions.append(str(d))
    for d in attendance_qs.values_list("date__year", flat=True):
        if d: all_sessions.append(str(d))
    all_sessions = sorted(set(all_sessions))
    all_levels = sorted({l for l in results_qs.values_list("level", flat=True) if l} |
                        {l for l in taken_qs.values_list("course__level", flat=True) if l} |
                        ({student.level} if student.level else set()))

    if level:
        results_qs = results_qs.filter(level=level)
        taken_qs = taken_qs.filter(course__level=level)
        # keep attendance/fees broad unless user expects level filter; level not stored on all, so filter loosely where possible
        decisions_qs = decisions_qs.filter(level=level)
    if session:
        results_qs = results_qs.filter(session=session)
        decisions_qs = decisions_qs.filter(session=session)
        fees_qs = fees_qs.filter(term__year=session)
        payments_qs = payments_qs.filter(payment_date__year=session)
        attendance_qs = attendance_qs.filter(date__year=session)
        attendance_summary_qs = attendance_summary_qs.filter(term__year=session)
    if term:
        results_qs = results_qs.filter(term=term)
        taken_qs = taken_qs.filter(course__term=term)
        # attendance has date; fees/payments have term relation
        fees_qs = fees_qs.filter(term__term=term)
        payments_qs = payments_qs.filter(assignment__term__term=term)

    # Group taken courses by (session, term, level)
    # Try to infer session/level from matching Result for same student/term
    result_map = {}
    for r in Result.objects.filter(student=student, school=school):
        result_map[(r.session, r.term, r.level)] = r
    # fallback: by term+level latest
    result_by_term_level = {}
    for r in Result.objects.filter(student=student, school=school).order_by("session"):
        result_by_term_level[(r.term, r.level)] = r

    grouped = {}
    for tc in taken_qs.order_by("course__level", "course__term", "course__title"):
        # find best matching result
        match = None
        for (s,t,l), r in result_map.items():
            if t == tc.course.term and l == tc.course.level:
                if (not level or l == level) and (not session or s == session) and (not term or t == term):
                    match = r; break
        if not match:
            match = result_by_term_level.get((tc.course.term, tc.course.level))
        sess = match.session if match else (session or "")
        lvl = tc.course.level or (match.level if match else "")
        trm = tc.course.term
        if level and lvl and lvl != level: continue
        if session and sess and sess != session: continue
        if term and trm and trm != term: continue
        key = (sess, trm, lvl)
        grouped.setdefault(key, {"session": sess, "term": trm, "level": lvl, "courses": [], "result": match})
        grouped[key]["courses"].append(tc)
    # also include results with no taken courses shown
    for r in results_qs.order_by("session", "term", "level"):
        key = (r.session, r.term, r.level)
        grouped.setdefault(key, {"session": r.session, "term": r.term, "level": r.level, "courses": [], "result": r})
        grouped[key]["result"] = r
    # sort groups
    term_order = {getattr(settings, 'FIRST_TERM', 'First'):1, getattr(settings,'SECOND_TERM','Second'):2, getattr(settings,'THIRD_TERM','Third'):3}
    academic_groups = sorted(grouped.values(), key=lambda g: (g.get('session') or '', term_order.get(g.get('term'), 9), g.get('level') or ''))

    attendance_totals = {
        "present": attendance_qs.filter(status__iexact="Present").count(),
        "absent": attendance_qs.filter(status__iexact="Absent").count(),
        "late": attendance_qs.filter(status__iexact="Late").count(),
        "excused": attendance_qs.filter(status__iexact="Excused").count(),
        "total": attendance_qs.count(),
    }
    fees_total = fees_qs.aggregate(total=Sum('amount'))['total'] or 0
    paid_total = payments_qs.filter(status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0

    class_transfers = list(
        student.class_transfers.select_related("transferred_by").order_by(
            "created_at"
        )
    )
    transfer_chain = ""
    if class_transfers:
        transfer_chain = " → ".join(
            [class_transfers[0].from_label]
            + [transfer.to_label for transfer in class_transfers]
        )

    return {
        "history_filters": {"level": level or "", "session": session or "", "term": term or ""},
        "history_levels": all_levels,
        "history_sessions": all_sessions,
        "history_terms": [t for t,_ in settings.TERM_CHOICES],
        "history_academic_groups": academic_groups,
        "history_results": results_qs.order_by("session", "term", "level"),
        "history_decisions": decisions_qs.order_by("session", "level"),
        "history_attendance": attendance_qs.order_by("-date")[:500],
        "history_attendance_summaries": attendance_summary_qs.order_by("-term__year", "term__term"),
        "history_attendance_totals": attendance_totals,
        "history_fees": fees_qs.order_by("-term__year", "term__term", "fee_structure__name"),
        "history_payments": payments_qs.order_by("-payment_date", "-created_at"),
        "history_fees_total": fees_total,
        "history_paid_total": paid_total,
        "history_balance_total": (fees_total - paid_total),
        "history_admission_date": admission_date,
        "history_exit_session": getattr(student, "exit_session", None),
        "history_exit_date": getattr(student, "exit_date", None),
        "history_class_transfers": class_transfers,
        "history_transfer_chain": transfer_chain,
    }


@login_required
def profile_single(request, user_id):
    """Show profile of any selected user. Accessible to admin/teachers in school and to the user/parent for student profiles."""
    if request.user.id == user_id:
        return redirect("profile")

    current_term = Semester.objects.filter(
        is_current_term=True, school=request.school
    ).first()
    user = get_object_or_404(User, pk=user_id, school=request.school)

    # Permission: admins/school admins/lecturers can view users in their school; students/parents only their own/child student profile
    is_admin_like = request.user.is_superuser or request.user.is_school_admin
    is_teacher = getattr(request.user, "is_lecturer", False) or getattr(request.user, "is_teacher", False)
    allowed = is_admin_like or is_teacher
    if not allowed and request.user.is_student and user.is_student and request.user.id == user.id:
        allowed = True
    if not allowed and request.user.is_parent and user.is_student:
        try:
            viewer_student = Student.objects.get(student__pk=request.user.id)
        except Student.DoesNotExist:
            viewer_student = None
        # parent accounts are separate User records in this project; allow if parent linked to this student
        if Parent.objects.filter(student__student=user, user=request.user).exists():
            allowed = True
    # also allow any authenticated user who is parent of that student via Parent model
    if not allowed and user.is_student and Parent.objects.filter(student__student=user, user=request.user).exists():
        allowed = True
    # students can view their own profile_single? redirected above. parents - Parent.user is parent user
    if not allowed:
        messages.error(request, "You do not have permission to view this profile.")
        return redirect("home")

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
        level = request.GET.get("level") or None
        session = request.GET.get("session") or None
        term = request.GET.get("term") or None
        context.update(
            {
                "user_type": "Student",
                "courses": courses,
                "student": student,
                "parent": parent,
            }
        )
        context.update(_build_student_history_context(student, request.school, level=level, session=session, term=term))
    else:
        context["user_type"] = "Superuser"

    if request.GET.get("download_pdf"):
        return render_to_pdf("pdf/profile_single.html", context)

    return render(request, "accounts/profile_single.html", context)


@login_required
@admin_required
def admin_panel(request):
    reset_events = PasswordResetAudit.objects.select_related("target_user", "performed_by")
    if not request.user.is_superuser:
        reset_events = reset_events.filter(school=request.school)
    return render(request, "setting/admin_panel.html", {
        "title": "Admin Panel",
        "password_reset_events": reset_events[:10],
    })


# ########################################################
# School Administrator Management
# ########################################################


@login_required
@school_admin_required
def school_admin_list(request):
    """List the administrators belonging to the current school only."""
    admins = User.objects.filter(
        is_school_admin=True,
        school=request.school,
    ).order_by("first_name", "last_name", "username")
    query = request.GET.get("q", "").strip()
    if query:
        admins = admins.filter(
            build_search_query(query, ["first_name", "last_name", "username", "email", "phone"])
        )
    return render(request, "accounts/school_admin_list.html", {
        "title": "School Administrators",
        "school_admins": admins,
        "search_query": query,
    })


@login_required
@school_admin_required
def school_admin_add(request):
    """Let a school admin add another admin to their own school."""
    if not request.school:
        messages.error(request, "Select a school before adding an administrator.")
        return redirect("admin_panel")

    if request.method == "POST":
        form = SchoolAdminAddForm(request.POST, school=request.school)
        if form.is_valid():
            new_admin = form.save()
            return render_credential_handoff(
                request,
                new_admin,
                form.temporary_password,
                reverse("school_admin_list"),
            )
        messages.error(request, "Please correct the error(s) below.")
    else:
        form = SchoolAdminAddForm(school=request.school)

    return render(request, "accounts/school_admin_form.html", {
        "title": "Add School Administrator",
        "form": form,
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
                defaults={"title": get_division_labels(request.school).get(division)},
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
        
        icons = {
            settings.DIVISION_NURSERY: "fas fa-baby",
            settings.DIVISION_PRIMARY: "fas fa-child",
            settings.DIVISION_JHS: "fas fa-user-graduate",
        }
        teacher_divisions = []
        for key, label in get_division_choices(self.request.school):
            teacher_divisions.append({
                "key": key,
                "label": label,
                "icon": icons.get(key, "fas fa-layer-group"),
                "teachers": filtered_qs.filter(division=key),
            })
        context["teacher_divisions"] = teacher_divisions
        # Preserve the legacy context keys used by existing tests/integrations.
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
            build_search_query(
                query,
                [
                    "first_name",
                    "last_name",
                    "other_names",
                    "username",
                    "email",
                    "phone",
                    "non_teaching_position",
                ],
            )
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
        department_title = get_division_labels(request.school).get(division)
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


def _tabular_export_response(columns, rows, title, filename, file_type, row_titles=None):
    """Return a styled Excel or Word document built from tabular rows."""
    if file_type == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title[:31]
        sheet.append([heading for heading, _ in columns])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24476B")
        for row in rows:
            sheet.append(row)
        for column_cells in sheet.columns:
            lengths = [len(str(cell.value or "")) for cell in column_cells[:100]]
            sheet.column_dimensions[column_cells[0].column_letter].width = min(
                max(max(lengths, default=10) + 2, 12), 32
            )
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        output = BytesIO()
        workbook.save(output)
        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response

    document = Document()
    document.add_heading(title, 0)
    for index, values in enumerate(rows, start=1):
        row_title = row_titles[index - 1] if row_titles else str(index)
        document.add_heading(f"{index}. {row_title}", level=1)
        table = document.add_table(rows=0, cols=2)
        table.style = "Light Shading Accent 1"
        for (heading, _), value in zip(columns, values):
            cells = table.add_row().cells
            cells[0].text = heading
            cells[1].text = str(value)
    output = BytesIO()
    document.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.docx"'
    return response


@login_required
@admin_required
def export_staff(request, staff_type, file_type):
    if staff_type not in {"teachers", "non-teaching"} or file_type not in {"xlsx", "docx"}:
        return HttpResponse(status=404)
    staff = list(_staff_queryset(request, staff_type))
    title = "Teachers" if staff_type == "teachers" else "Non-teaching Staff"
    rows = [
        [_staff_export_value(person, field) for _, field in STAFF_EXPORT_COLUMNS]
        for person in staff
    ]
    return _tabular_export_response(
        STAFF_EXPORT_COLUMNS,
        rows,
        title,
        f"{staff_type}_staff",
        file_type,
        row_titles=[person.get_full_name for person in staff],
    )


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
                        if division and not is_known_division(division, request.school):
                            errors.append(f"Row {row_number}: choose a valid division.")
                        elif level and division and level not in get_levels_for_division(
                            division, school=request.school
                        ):
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
                                title = get_division_labels(request.school)[values["division"]]
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


# ########################################################
# Student Excel/Word export and Excel import
# ########################################################


STUDENT_EXPORT_COLUMNS = (
    ("Username", "username"),
    ("First name", "first_name"),
    ("Other names", "other_names"),
    ("Last name", "last_name"),
    ("Gender", "gender"),
    ("Date of birth", "date_of_birth"),
    ("Place of birth", "place_of_birth"),
    ("Nationality", "nationality"),
    ("Hometown", "hometown"),
    ("Region", "region"),
    ("District", "district"),
    ("Religion", "religion"),
    ("Ghana Card number", "ghana_card_number"),
    ("NHIS number", "nhis_number"),
    ("GhanaPost GPS address", "gps_address"),
    ("Phone", "phone"),
    ("Alternate phone", "alternate_phone"),
    ("Email", "email"),
    ("Residential address", "address"),
    ("Admission number", "admission_number"),
    ("Admission date", "admission_date"),
    ("Previous school", "previous_school"),
    ("Previous class", "previous_class"),
    ("BECE year", "bece_year"),
    ("BECE index number", "bece_index_number"),
    ("BECE aggregate", "bece_aggregate"),
    ("Birth certificate number", "birth_certificate_number"),
    ("Boarding status", "boarding_status"),
    ("Guardian name", "guardian_name"),
    ("Guardian relationship", "guardian_relationship"),
    ("Guardian phone", "guardian_phone"),
    ("Guardian email", "guardian_email"),
    ("Guardian occupation", "guardian_occupation"),
    ("Guardian address", "guardian_address"),
    ("Guardian Ghana Card", "guardian_ghana_card"),
    ("Second guardian name", "second_guardian_name"),
    ("Second guardian relationship", "second_guardian_relationship"),
    ("Second guardian phone", "second_guardian_phone"),
    ("Second guardian occupation", "second_guardian_occupation"),
    ("Blood group", "blood_group"),
    ("Medical conditions", "medical_conditions"),
    ("Allergies", "allergies"),
    ("Special needs", "special_needs"),
    ("Emergency contact name", "emergency_contact_name"),
    ("Emergency contact relationship", "emergency_contact_relationship"),
    ("Emergency contact phone", "emergency_contact_phone"),
    ("Emergency contact address", "emergency_contact_address"),
    ("Class / Level", "level"),
    ("Sub-class / Arm", "sub_class"),
    ("Program", "program"),
    ("House", "house"),
    ("Status", "status"),
)

STUDENT_RECORD_FIELDS = frozenset({"level", "sub_class", "program", "house", "status"})
STUDENT_IMPORT_COLUMNS = [field for _, field in STUDENT_EXPORT_COLUMNS]
STUDENT_REQUIRED_IMPORT_COLUMNS = {"first_name", "last_name", "level"}
# These are looked up against the school's own programmes/sub-classes instead
# of being cleaned directly from the workbook cell.
STUDENT_LOOKUP_FIELDS = {"sub_class", "program", "username"}
STUDENT_CLEAN_IMPORT_FIELDS = tuple(
    field for field in STUDENT_IMPORT_COLUMNS if field not in STUDENT_LOOKUP_FIELDS
)
STUDENT_USER_IMPORT_FIELDS = tuple(
    field for field in STUDENT_CLEAN_IMPORT_FIELDS if field not in STUDENT_RECORD_FIELDS
)


def _student_queryset(request):
    """Mirror the student list so exports respect the current school/filter."""
    qs = Student.objects.filter(student__school=request.school).select_related(
        "student", "program", "sub_class"
    )
    if not request.GET.get("status"):
        qs = qs.filter(status=STUDENT_STATUS_ACTIVE)
    return qs


def _student_export_value(student, field):
    if field == "sub_class":
        return student.sub_class.name if student.sub_class_id else ""
    if field == "program":
        return student.program.title if student.program_id else ""
    if field in STUDENT_RECORD_FIELDS:
        record, model = student, Student
    else:
        record, model = student.student, User
    value = getattr(record, field, "")
    if value in (None, ""):
        return ""
    if model._meta.get_field(field).choices:
        return getattr(record, f"get_{field}_display")()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _clean_student_import_value(field_name, value):
    model = Student if field_name in STUDENT_RECORD_FIELDS else User
    model_field = model._meta.get_field(field_name)
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
def export_students(request, file_type):
    if file_type not in {"xlsx", "docx"}:
        return HttpResponse(status=404)
    students = list(_student_queryset(request))
    rows = [
        [_student_export_value(student, field) for _, field in STUDENT_EXPORT_COLUMNS]
        for student in students
    ]
    return _tabular_export_response(
        STUDENT_EXPORT_COLUMNS,
        rows,
        "Students",
        "students",
        file_type,
        row_titles=[student.student.get_full_name for student in students],
    )


@login_required
@admin_required
def import_students(request):
    errors = []
    imported = 0
    if request.method == "POST" and request.FILES.get("workbook"):
        try:
            workbook = load_workbook(request.FILES["workbook"], read_only=True, data_only=True)
            sheet = workbook.active
            rows = sheet.iter_rows(values_only=True)
            headers = [str(value or "").strip().lower() for value in next(rows, ())]
            missing = STUDENT_REQUIRED_IMPORT_COLUMNS - set(headers)
            if missing:
                errors.append("Missing required columns: " + ", ".join(sorted(missing)))
            else:
                positions = {
                    name: headers.index(name) for name in STUDENT_IMPORT_COLUMNS if name in headers
                }
                data = []
                seen_usernames = set()
                seen_admission_numbers = set()
                for row_number, row in enumerate(rows, start=2):
                    values = {
                        name: (row[index] if index < len(row) else None)
                        for name, index in positions.items()
                    }
                    for field_name in STUDENT_IMPORT_COLUMNS:
                        values.setdefault(field_name, None)
                    if not any(value not in (None, "") for value in values.values()):
                        continue
                    for phone_field in (
                        "phone", "alternate_phone", "guardian_phone",
                        "second_guardian_phone", "emergency_contact_phone",
                    ):
                        raw_phone = values.get(phone_field)
                        if (
                            isinstance(raw_phone, (int, float))
                            and str(int(raw_phone)).isdigit()
                            and len(str(int(raw_phone))) == 9
                        ):
                            values[phone_field] = f"0{int(raw_phone)}"
                    values = {
                        name: value.date().isoformat() if isinstance(value, datetime)
                        else value.isoformat() if isinstance(value, date)
                        else str(value).strip() if value is not None else ""
                        for name, value in values.items()
                    }
                    cleaned = {}
                    row_errors = []
                    if not values["first_name"] or not values["last_name"]:
                        row_errors.append("first_name and last_name are required.")
                    if not values["level"]:
                        row_errors.append("level is required.")
                    for field_name in STUDENT_CLEAN_IMPORT_FIELDS:
                        try:
                            cleaned[field_name] = _clean_student_import_value(
                                field_name, values[field_name]
                            )
                        except Exception as exc:
                            row_errors.append(f"{field_name}: {exc}")

                    username = values["username"].strip()
                    if username and User.objects.filter(username__iexact=username).exists():
                        row_errors.append(f"username {username} already exists.")
                    elif username and username.casefold() in seen_usernames:
                        row_errors.append(f"username {username} is repeated in this workbook.")

                    admission_number = str(cleaned.get("admission_number") or "").strip()
                    if admission_number and User.objects.filter(
                        school=request.school, admission_number__iexact=admission_number
                    ).exists():
                        row_errors.append(f"admission_number {admission_number} already exists.")
                    elif admission_number and admission_number.casefold() in seen_admission_numbers:
                        row_errors.append(
                            f"admission_number {admission_number} is repeated in this workbook."
                        )

                    program_title = values["program"].strip()
                    if program_title:
                        program = Program.objects.filter(
                            school=request.school, title__iexact=program_title
                        ).first()
                        if not program:
                            row_errors.append(
                                f"program {program_title} does not exist in this school."
                            )
                        else:
                            cleaned["program_id"] = program.pk
                    else:
                        cleaned["program_id"] = None

                    sub_class_name = values["sub_class"].strip()
                    if sub_class_name:
                        sub_class = SubClass.objects.filter(
                            school=request.school,
                            level=cleaned.get("level"),
                            name__iexact=sub_class_name,
                        ).first()
                        if not sub_class:
                            row_errors.append(
                                f"sub_class {sub_class_name} is not configured for "
                                f"{values['level']} in this school."
                            )
                        else:
                            cleaned["sub_class_id"] = sub_class.pk
                    else:
                        cleaned["sub_class_id"] = None

                    if row_errors:
                        errors.extend(f"Row {row_number}: {error}" for error in row_errors)
                        continue

                    cleaned["username"] = username
                    cleaned["status"] = cleaned.get("status") or STUDENT_STATUS_ACTIVE
                    if username:
                        seen_usernames.add(username.casefold())
                    if admission_number:
                        seen_admission_numbers.add(admission_number.casefold())
                    data.append(cleaned)

                if not errors:
                    with transaction.atomic():
                        for values in data:
                            division = get_division_for_level(values["level"], school=request.school)
                            username = values["username"] or generate_student_credentials(
                                school=request.school, division=division
                            )[0]
                            user = User.objects.create_user(
                                username=username,
                                password=User.objects.make_random_password(length=16),
                                school=request.school,
                                is_student=True,
                                must_change_password=True,
                            )
                            for field_name in STUDENT_USER_IMPORT_FIELDS:
                                setattr(user, field_name, values.get(field_name))
                            if not user.admission_number:
                                user.admission_number = username
                            if not user.admission_date:
                                user.admission_date = timezone.localdate()
                            user.save()
                            Student.objects.create(
                                student=user,
                                level=values["level"],
                                sub_class_id=values["sub_class_id"],
                                program_id=values["program_id"],
                                house=values.get("house") or None,
                                status=values["status"],
                            )
                            imported += 1
                    messages.success(
                        request,
                        f"Imported {imported} student account(s). Temporary passwords must be "
                        "reset by an administrator before first sign-in.",
                    )
                    return redirect("student_list")
        except Exception as exc:
            errors.append(f"Could not read this Excel workbook: {exc}")
    return render(request, "accounts/import_students.html", {
        "title": "Import students from Excel", "errors": errors,
        "import_columns": STUDENT_IMPORT_COLUMNS,
    })


@login_required
@admin_required
def download_student_import_template(request):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Student import"
    sheet.append(STUDENT_IMPORT_COLUMNS)
    program_title = Program.objects.filter(
        school=request.school, is_academic_block=True
    ).values_list("title", flat=True).first() or ""
    sub_class_name = SubClass.objects.filter(
        school=request.school, level="Primary 1"
    ).values_list("name", flat=True).first() or ""
    example = {
        "first_name": "Ama", "last_name": "Mensah", "gender": "F",
        "date_of_birth": "2012-05-14", "phone": "0200000000", "address": "Accra",
        "level": "Primary 1", "program": program_title, "sub_class": sub_class_name,
        "house": "Red", "status": "Active", "guardian_name": "Kwame Mensah",
        "guardian_relationship": "Father", "guardian_phone": "0240000000",
    }
    sheet.append([example.get(column, "") for column in STUDENT_IMPORT_COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DCEAF7")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for field_name in {
        "phone", "alternate_phone", "guardian_phone", "second_guardian_phone",
        "emergency_contact_phone", "ghana_card_number", "nhis_number",
        "guardian_ghana_card", "bece_index_number", "birth_certificate_number",
        "admission_number",
    }:
        if field_name in STUDENT_IMPORT_COLUMNS:
            column_index = STUDENT_IMPORT_COLUMNS.index(field_name) + 1
            sheet.cell(row=2, column=column_index).number_format = "@"
    for column_cells in sheet.columns:
        lengths = [len(str(cell.value or "")) for cell in column_cells[:3]]
        letter = column_cells[0].column_letter
        sheet.column_dimensions[letter].width = max(
            min(max(lengths) + 2, 28), sheet.column_dimensions[letter].width or 10
        )
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="student_import_template.xlsx"'
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

        # Pre-fill the sub-class when the admin acted from a filtered roster.
        sub_class_param = request.GET.get("sub_class")
        if sub_class_param:
            try:
                sub_class = SubClass.objects.filter(
                    school=request.school, pk=sub_class_param, is_active=True
                ).first()
            except (TypeError, ValueError):
                sub_class = None
            if sub_class:
                initial_data["sub_class"] = sub_class
                initial_data.setdefault("level", sub_class.level)

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


def _division_links(request, url_name, drop_params=()):
    """Division selector links that preserve the other active query params."""
    params = request.GET.copy()
    for name in ("page",) + tuple(drop_params):
        params.pop(name, None)

    icons = {
        "": "fas fa-layer-group",
        settings.DIVISION_NURSERY: "fas fa-baby",
        settings.DIVISION_PRIMARY: "fas fa-child",
        settings.DIVISION_JHS: "fas fa-user-graduate",
    }
    options = (("", "All divisions"),) + tuple(
        get_division_choices(getattr(request, "school", None))
    )
    links = []
    for key, label in options:
        link_params = params.copy()
        if key:
            link_params["division"] = key
        else:
            link_params.pop("division", None)
        query = link_params.urlencode()
        url = reverse(url_name)
        if query:
            url = f"{url}?{query}"
        links.append({
            "key": key,
            "label": label,
            "icon": icons.get(key, "fas fa-layer-group"),
            "url": url,
            "is_all": not key,
        })
    return links


@method_decorator([login_required, admin_required], name="dispatch")
class StudentListView(FilterView):
    filterset_class = StudentFilter
    template_name = "accounts/student_list.html"
    paginate_by = 10

    def get_queryset(self):
        qs = Student.objects.filter(
            student__school=self.request.school
        ).select_related("student", "program", "sub_class")
        status = self.request.GET.get("status")
        if not status:
            qs = qs.filter(status=STUDENT_STATUS_ACTIVE)
        return qs

    def get_filterset_kwargs(self, filterset_class):
        kwargs = super().get_filterset_kwargs(filterset_class)
        kwargs["school"] = self.request.school
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Students"

        qs = Student.objects.filter(student__school=self.request.school).select_related(
            "student", "program"
        )
        status = self.request.GET.get("status")
        if not status:
            qs = qs.filter(status=STUDENT_STATUS_ACTIVE)
        filtered_qs = self.filterset_class(
            self.request.GET, queryset=qs, school=self.request.school
        ).qs

        division_choices = get_division_choices(self.request.school)
        valid_divisions = dict(division_choices)
        division_students = {
            key: filtered_qs.filter(student__division=key)
            for key in valid_divisions
        }
        context["division_students"] = division_students
        # Keep the original names for existing templates/tests.
        context["nursery_students"] = division_students.get(settings.DIVISION_NURSERY, [])
        context["primary_students"] = division_students.get(settings.DIVISION_PRIMARY, [])
        context["jhs_students"] = division_students.get(settings.DIVISION_JHS, [])
        context["other_students"] = filtered_qs.filter(
            student__division__isnull=True
        )

        active_division = self.request.GET.get("division", "")
        if active_division not in valid_divisions:
            active_division = ""
        context["active_division"] = active_division
        context["division_tabs"] = _division_links(
            self.request, "student_list", drop_params=("sub_class",)
        )
        context["active_division_label"] = next(
            (
                tab["label"]
                for tab in context["division_tabs"]
                if tab["key"] == active_division
            ),
            "All divisions",
        )
        context["clear_filters_url"] = reverse("student_list")
        if active_division:
            context["clear_filters_url"] += f"?division={active_division}"

        context["active_students"] = (
            division_students[active_division]
            if active_division
            else filtered_qs
        )

        return context


@login_required
@admin_required
def render_student_pdf_list(request):
    students = Student.objects.filter(
        student__school=request.school,
        status=STUDENT_STATUS_ACTIVE,
    )
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
def student_transfer_view(request, pk):
    """Move a learner to another sub-class (and optionally another class)."""
    student = get_object_or_404(Student, pk=pk, student__school=request.school)
    student_name = student.student.get_full_name or student.student.username

    if request.method == "POST":
        form = StudentTransferForm(
            request.POST, school=request.school, student=student
        )
        if form.is_valid():
            target_level = form.cleaned_data["to_level"]
            target_sub_class = form.cleaned_data["to_sub_class"]
            previous_class = student.class_label or "Unassigned"
            new_class = (
                f"{target_level} {target_sub_class.name}".strip()
            )

            with transaction.atomic():
                ClassTransfer.objects.create(
                    student=student,
                    from_level=student.level or "",
                    from_sub_class_name=(
                        student.sub_class.name if student.sub_class_id else ""
                    ),
                    from_sub_class=student.sub_class,
                    to_level=target_level,
                    to_sub_class_name=target_sub_class.name,
                    to_sub_class=target_sub_class,
                    note=form.cleaned_data.get("note", ""),
                    transferred_by=request.user,
                )
                student.level = target_level
                student.sub_class = target_sub_class
                student.save()

            messages.success(
                request,
                f"Transferred {student_name} from {previous_class} to {new_class}.",
            )
            return redirect(
                f"{reverse('class_detail', args=[target_level])}"
                f"?sub_class={target_sub_class.pk}"
            )
        messages.error(request, "Please correct the error below.")
    else:
        form = StudentTransferForm(school=request.school, student=student)

    return render(
        request,
        "accounts/transfer_student.html",
        {
            "title": f"Transfer {student_name}",
            "student": student,
            "form": form,
            "current_class": student.class_label or "Unassigned",
        },
    )


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
    is_admin = request.user.is_superuser or request.user.is_school_admin

    if is_admin:
        # Admins see all classes
        levels = get_level_choices(request.school)
    elif request.user.division:
        # Teachers see only classes in their assigned division
        accessible_levels = request.user.get_division_levels()
        levels = [
            (code, name) for code, name in get_level_choices(request.school)
            if code in accessible_levels
        ]
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
        count = Student.objects.filter(
            level=level_code,
            student__school=request.school,
            status=STUDENT_STATUS_ACTIVE,
        ).count()
        students_counts[level_code] = count

    # Sub-classes (for example Primary 1A / 1B) are managed per class level.
    level_codes = [code for code, _ in levels]
    sub_classes = SubClass.objects.filter(
        school=request.school, is_active=True
    ).annotate(
        roster_count=Count(
            "students", filter=Q(students__status=STUDENT_STATUS_ACTIVE)
        )
    ).order_by("level", "display_order", "name")
    sub_classes_by_level = {code: [] for code in level_codes}
    for sub_class in sub_classes:
        if sub_class.level in sub_classes_by_level:
            sub_classes_by_level[sub_class.level].append(sub_class)

    valid_divisions = dict(get_division_choices(request.school))
    active_division = request.GET.get("division", "")
    if active_division not in valid_divisions:
        active_division = ""
    if not active_division and not is_admin and request.user.division in valid_divisions:
        active_division = request.user.division

    division_tabs = _division_links(request, "class_list")
    if not is_admin and request.user.division:
        division_tabs = [
            tab for tab in division_tabs
            if tab["is_all"] or tab["key"] == request.user.division
        ]

    division_levels = get_levels_for_division(active_division, school=request.school)
    active_levels = [
        (code, name) for code, name in levels
        if not active_division or code in division_levels
    ]
    clear_filters_url = reverse("class_list")
    if active_division:
        clear_filters_url += f"?division={active_division}"

    context = {
        "title": "Manage Classes",
        "levels": levels,
        "active_levels": active_levels,
        "students_counts": students_counts,
        "sub_classes_by_level": sub_classes_by_level,
        "is_teacher": not is_admin,
        "user_division": request.user.division if hasattr(request.user, 'division') else None,
        "division_tabs": division_tabs,
        "active_division": active_division,
        "active_division_label": next(
            (tab["label"] for tab in division_tabs if tab["key"] == active_division),
            "All divisions",
        ),
        "clear_filters_url": clear_filters_url,
    }
    return render(request, "accounts/class_list.html", context)


@login_required
@lecturer_required
def class_detail_view(request, level_code):
    """Workspace for a specific class level - with division-based access control"""
    
    # Find level name from choices
    level_name = dict(get_level_choices(request.school)).get(level_code, level_code)

    # Access Control: Verify teacher can access this level based on division
    if not request.user.can_access_level(level_code):
        level_division = get_division_for_level(level_code, school=request.school)
        
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
        level=level_code,
        student__school=request.school,
        status=STUDENT_STATUS_ACTIVE,
    ).select_related('student', 'program', 'sub_class')

    # Sub-classes for this level and their roster counts.
    sub_classes = list(
        SubClass.objects.filter(
            school=request.school, level=level_code, is_active=True
        ).order_by("display_order", "name")
    )
    sub_class_counts = {
        row["sub_class_id"]: row["count"]
        for row in students.exclude(sub_class__isnull=True)
        .values("sub_class_id")
        .annotate(count=Count("id"))
    }
    unassigned_count = students.filter(sub_class__isnull=True).count()
    total_students = students.count()
    for sub_class in sub_classes:
        sub_class.roster_count = sub_class_counts.get(sub_class.pk, 0)

    # Optional roster filter: ?sub_class=<id> or ?sub_class=unassigned
    roster_filter = (request.GET.get("sub_class") or "").strip()
    selected_sub_class = None
    if roster_filter == "unassigned":
        students = students.filter(sub_class__isnull=True)
    elif roster_filter:
        try:
            selected_sub_class = next(
                (item for item in sub_classes if str(item.pk) == roster_filter), None
            )
        except (TypeError, ValueError):
            selected_sub_class = None
        if selected_sub_class:
            students = students.filter(sub_class=selected_sub_class)

    current_term = Semester.objects.filter(is_current_term=True, school=request.school).first()
    is_third_term = current_term and current_term.term == settings.THIRD_TERM

    level_division = get_division_for_level(level_code, school=request.school)
    level_teachers = User.objects.filter(
        school=request.school,
        is_teacher=True,
        is_active=True,
        division=level_division,
    ).order_by("first_name", "last_name")
    
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
        "active_tab": "subclasses" if request.GET.get("tab") == "subclasses" else "roster",
        "sub_classes": sub_classes,
        "sub_class_counts": sub_class_counts,
        "unassigned_count": unassigned_count,
        "total_students": total_students,
        "roster_filter": roster_filter,
        "selected_sub_class": selected_sub_class,
        "level_teachers": level_teachers,
        "current_term": current_term,
        "is_third_term": is_third_term,
        "broadsheet_data": broadsheet_data,
        "is_teacher": not (request.user.is_superuser or request.user.is_school_admin),
    }
    return render(request, "accounts/class_detail.html", context)


def _sub_class_letters(index):
    """Return spreadsheet-style labels: 1 -> A, 26 -> Z, 27 -> AA."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    label = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        label = letters[remainder] + label
    return label


def _next_sub_class_names(existing_names, count, scheme):
    """Pick the next available sub-class names without reusing existing ones."""
    existing = {str(name).strip().lower() for name in existing_names}
    names = []

    if scheme == "numbers":
        numeric = [int(name) for name in existing if name.isdigit()]
        candidate = max(numeric, default=0) + 1
        while len(names) < count:
            name = str(candidate)
            if name.lower() not in existing:
                names.append(name)
            candidate += 1
        return names

    candidate = 1
    while len(names) < count:
        name = _sub_class_letters(candidate)
        if name.lower() not in existing:
            names.append(name)
        candidate += 1
    return names


def _validated_level_code(level_code, school=None):
    """Validate a level against this school's configured classes."""
    codes = {code for code, _ in get_level_choices(school)}
    return level_code if level_code in codes else None


def _sub_class_manager_redirect(level_code):
    """Return to the class workspace with the sub-class manager tab open."""
    return redirect(
        f"{reverse('class_detail', args=[level_code])}?tab=subclasses"
    )


@login_required
@admin_required
@require_POST
def sub_class_create(request, level_code):
    """Create one sub-class (arm) for a class level."""
    level_code = _validated_level_code(level_code, school=request.school)
    if not level_code:
        messages.error(request, "Invalid class level.")
        return redirect("class_list")

    form = SubClassForm(request.POST, school=request.school, level=level_code)
    if form.is_valid():
        sub_class = form.save(commit=False)
        sub_class.school = request.school
        sub_class.level = level_code
        last_order = SubClass.objects.filter(
            school=request.school, level=level_code
        ).aggregate(Max("display_order"))["display_order__max"] or 0
        sub_class.display_order = last_order + 1
        sub_class.save()
        messages.success(
            request, f"Sub-class '{sub_class.name}' added to {level_code}."
        )
    else:
        first_error = next(iter(form.errors.values()))[0]
        messages.error(request, first_error)
    return _sub_class_manager_redirect(level_code)


@login_required
@admin_required
@require_POST
def sub_class_bulk_create(request, level_code):
    """Create several sub-classes for a class level in one request."""
    level_code = _validated_level_code(level_code, school=request.school)
    if not level_code:
        messages.error(request, "Invalid class level.")
        return redirect("class_list")

    form = BulkSubClassForm(request.POST)
    if form.is_valid():
        count = form.cleaned_data["count"]
        scheme = form.cleaned_data["scheme"]
        capacity = form.cleaned_data.get("capacity")
        existing_names = list(
            SubClass.objects.filter(
                school=request.school, level=level_code
            ).values_list("name", flat=True)
        )
        names = _next_sub_class_names(existing_names, count, scheme)
        last_order = SubClass.objects.filter(
            school=request.school, level=level_code
        ).aggregate(Max("display_order"))["display_order__max"] or 0

        created = []
        with transaction.atomic():
            for offset, name in enumerate(names, start=1):
                created.append(
                    SubClass(
                        school=request.school,
                        level=level_code,
                        name=name,
                        capacity=capacity,
                        display_order=last_order + offset,
                    )
                )
            SubClass.objects.bulk_create(created)

        messages.success(
            request,
            f"Added {len(created)} sub-class(es) to {level_code}: "
            + ", ".join(names),
        )
    else:
        first_error = next(iter(form.errors.values()))[0]
        messages.error(request, first_error)
    return _sub_class_manager_redirect(level_code)


@login_required
@admin_required
@require_POST
def sub_class_edit(request, pk):
    """Rename a sub-class or update its capacity/class teacher."""
    sub_class = get_object_or_404(SubClass, pk=pk, school=request.school)
    level_code = sub_class.level
    form = SubClassForm(
        request.POST, instance=sub_class, school=request.school, level=level_code
    )
    if form.is_valid():
        form.save()
        messages.success(request, f"Sub-class '{sub_class.name}' updated.")
    else:
        first_error = next(iter(form.errors.values()))[0]
        messages.error(request, first_error)
    return _sub_class_manager_redirect(level_code)


@login_required
@admin_required
@require_POST
def sub_class_delete(request, pk):
    """Delete a sub-class; assigned students become unassigned, not deleted."""
    sub_class = get_object_or_404(SubClass, pk=pk, school=request.school)
    level_code = sub_class.level
    name = sub_class.name
    student_count = sub_class.students.count()
    sub_class.delete()
    if student_count:
        messages.warning(
            request,
            f"Sub-class '{name}' deleted. {student_count} student(s) are now "
            "unassigned and can be moved to another sub-class.",
        )
    else:
        messages.success(request, f"Sub-class '{name}' deleted.")
    return _sub_class_manager_redirect(level_code)
