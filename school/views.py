from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from django.core.mail import send_mail
from django.conf import settings

from .models import (
    School, SchoolDivision, SchoolDivisionOrder, GradeWeightConfig, PromotionPolicy,
)
from .forms import (
    SchoolForm, SchoolOnboardingForm, SchoolStatusForm,
    SchoolIdentityForm, SchoolDivisionForm, SchoolDivisionOrderForm,
    StudentIDFormatForm, GradeWeightForm, PromotionPolicyForm,
)
from .division_utils import get_division_choices
from accounts.models import User
from core.models import Notification
from core.notifications import notify, notify_admins


def is_superuser(user):
    return user.is_superuser


@method_decorator([login_required, user_passes_test(is_superuser)], name='dispatch')
class SchoolListView(ListView):
    model = School
    template_name = "school/school_list.html"
    context_object_name = "schools"


@method_decorator([login_required, user_passes_test(is_superuser)], name='dispatch')
class SchoolCreateView(CreateView):
    model = School
    form_class = SchoolOnboardingForm
    template_name = "school/school_form.html"
    success_url = reverse_lazy("school_list")

    def form_valid(self, form):
        school = form.save()
        temp_password = User.objects.make_random_password()
        admin_user = User.objects.create_user(
            username=f"{school.slug}_admin",
            email=form.cleaned_data['admin_email'],
            password=temp_password,
            first_name=form.cleaned_data['admin_first_name'],
            last_name=form.cleaned_data['admin_last_name'],
            is_school_admin=True,
            school=school,
            is_active=True
        )
        self.send_welcome_email(school, admin_user, temp_password)
        messages.success(
            self.request,
            f"School '{school.name}' created successfully. Welcome email sent to {admin_user.email}."
        )
        return super().form_valid(form)

    def send_welcome_email(self, school, admin_user, temp_password):
        subject = f"Welcome to SkyLearn - {school.name} Admin Account"
        message = (
            f"Dear {admin_user.get_full_name},\n\n"
            f"Your school '{school.name}' has been registered.\n\n"
            f"Username: {admin_user.username}\nTemporary Password: {temp_password}\n\n"
            "Please login and change your password immediately.\n\nThe SkyLearn Team"
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [admin_user.email], fail_silently=False)
        except Exception as e:
            print(f"Failed to send welcome email: {e}")


@method_decorator([login_required, user_passes_test(is_superuser)], name='dispatch')
class SchoolUpdateView(UpdateView):
    model = School
    form_class = SchoolForm
    template_name = "school/school_form.html"
    success_url = reverse_lazy("school_list")

    def form_valid(self, form):
        messages.success(self.request, "School updated successfully.")
        return super().form_valid(form)


@login_required
@user_passes_test(is_superuser)
def school_onboarding(request):
    if request.method == 'POST':
        form = SchoolOnboardingForm(request.POST)
        if form.is_valid():
            school = form.save()
            temp_password = User.objects.make_random_password()
            admin_user = User.objects.create_user(
                username=f"{school.slug}_admin",
                email=form.cleaned_data['admin_email'],
                password=temp_password,
                first_name=form.cleaned_data['admin_first_name'],
                last_name=form.cleaned_data['admin_last_name'],
                is_school_admin=True,
                school=school,
                is_active=True
            )
            messages.success(request, f"School '{school.name}' onboarded! Admin: {admin_user.username}")
            return redirect('school_list')
    else:
        form = SchoolOnboardingForm()
    return render(request, 'school/onboard.html', {'form': form, 'title': 'Onboard New School'})


def send_welcome_email(school, admin_user, temp_password):
    subject = f"Welcome to SkyLearn - {school.name} Admin Account"
    message = (
        f"Dear {admin_user.get_full_name},\n\n"
        f"Username: {admin_user.username}\nTemporary Password: {temp_password}\n\n"
        "The SkyLearn Team"
    )
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [admin_user.email], fail_silently=False)
    except Exception as e:
        print(f"Failed to send welcome email: {e}")


@login_required
@user_passes_test(is_superuser)
def school_switch(request, school_slug):
    school = get_object_or_404(School, slug=school_slug)
    request.session['school_slug'] = school.slug
    messages.success(request, f"Switched to {school.name}")
    return redirect("dashboard")


# ─────────────────────────────────────────────────────────────────────────────
# SCHOOL SETTINGS — Accessible to school admins
# ─────────────────────────────────────────────────────────────────────────────

def _school_admin_required(view_func):
    """Decorator: user must be school admin or superuser with an active school context."""
    from functools import wraps

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_superuser or request.user.is_school_admin):
            messages.error(request, _("You do not have permission to access school settings."))
            return redirect('dashboard')
        if not hasattr(request, 'school') or not request.school:
            messages.error(request, _("No school context found."))
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


@_school_admin_required
def school_settings(request):
    """Main settings hub — redirects to identity tab by default."""
    return redirect('school_settings_identity')


@_school_admin_required
def school_settings_identity(request):
    """School identity & branding settings tab."""
    school = request.school
    if request.method == 'POST':
        form = SchoolIdentityForm(request.POST, request.FILES, instance=school)
        if form.is_valid():
            form.save()
            messages.success(request, _("School identity updated successfully."))
            return redirect('school_settings_identity')
        else:
            messages.error(request, _("Please correct the errors below."))
    else:
        form = SchoolIdentityForm(instance=school)

    from result.models import PromotionRequest
    pending_count = PromotionRequest.objects.filter(school=school, status='PENDING').count()

    return render(request, 'school/school_settings.html', {
        'active_tab': 'identity',
        'form': form,
        'school': school,
        'pending_count': pending_count,
        'title': _('School Settings — Identity'),
    })


def _put_new_division_first(school, division_name):
    """Keep the current order but place a newly added division before it."""
    ordered_names = [name for name, _ in get_division_choices(school)]
    for index, name in enumerate(ordered_names):
        SchoolDivisionOrder.objects.update_or_create(
            school=school, division=name, defaults={"order": index + 1}
        )
    SchoolDivisionOrder.objects.update_or_create(
        school=school, division=division_name, defaults={"order": 0}
    )


@_school_admin_required
def school_settings_divisions(request):
    """Let a school admin add, arrange and edit divisions and their classes."""
    school = request.school
    divisions = school.custom_divisions.prefetch_related("levels").order_by("order", "name")
    form = SchoolDivisionForm(school=school)
    order_form = SchoolDivisionOrderForm(school=school)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "delete":
            division = get_object_or_404(
                SchoolDivision, pk=request.POST.get("division_id"), school=school
            )
            SchoolDivisionOrder.objects.filter(school=school, division=division.name).delete()
            division.delete()
            messages.success(request, _("Division removed."))
            return redirect("school_settings_divisions")

        if action == "save_order":
            order_form = SchoolDivisionOrderForm(request.POST, school=school)
            if order_form.is_valid():
                for index, name in enumerate(order_form.ordered_divisions()):
                    SchoolDivisionOrder.objects.update_or_create(
                        school=school, division=name, defaults={"order": index}
                    )
                messages.success(request, _("Division order saved."))
                return redirect("school_settings_divisions")
            messages.error(request, _("Please correct the division order."))
        else:
            division_id = request.POST.get("division_id") or None
            division = (
                get_object_or_404(SchoolDivision, pk=division_id, school=school)
                if division_id else None
            )
            is_new = division is None
            old_name = division.name if division else None
            form = SchoolDivisionForm(request.POST, school=school, division=division)
            if form.is_valid():
                if is_new:
                    division = SchoolDivision(school=school, order=divisions.count())
                division.name = form.cleaned_data["name"]
                division.id_prefix = form.cleaned_data["id_prefix"]
                division.id_pattern = form.cleaned_data["id_pattern"]
                division.save()

                if is_new:
                    _put_new_division_first(school, division.name)
                elif old_name != division.name:
                    SchoolDivisionOrder.objects.filter(
                        school=school, division=old_name
                    ).update(division=division.name)

                # The form is the source of truth for this division's classes.
                division.levels.all().delete()
                for index, level_name in enumerate(form.cleaned_data["levels"]):
                    division.levels.create(name=level_name, order=index)

                messages.success(request, _("Division saved."))
                return redirect("school_settings_divisions")
            messages.error(request, _("Please correct the errors below."))

    division_forms = [
        (
            division,
            SchoolDivisionForm(
                initial={
                    "division_id": division.pk,
                    "name": division.name,
                    "levels": "\n".join(level.name for level in division.levels.all()),
                    "id_prefix": division.id_prefix,
                    "id_pattern": division.id_pattern,
                },
                school=school,
                division=division,
            ),
        )
        for division in divisions
    ]

    from result.models import PromotionRequest
    pending_count = PromotionRequest.objects.filter(school=school, status='PENDING').count()

    return render(request, 'school/school_settings.html', {
        'active_tab': 'divisions',
        'division_form': form,
        'division_order_form': order_form,
        'division_forms': division_forms,
        'custom_divisions': divisions,
        'division_choices': get_division_choices(school),
        'school': school,
        'pending_count': pending_count,
        'title': _('School Settings — Divisions'),
    })


@_school_admin_required
def school_settings_student_ids(request):
    """Configure school-wide student ID generation patterns."""
    school = request.school
    if request.method == 'POST':
        student_id_format_form = StudentIDFormatForm(request.POST, instance=school)
        if student_id_format_form.is_valid():
            student_id_format_form.save()
            messages.success(request, _("Student ID formats saved."))
            return redirect('school_settings_student_ids')
        messages.error(request, _("Please correct the student ID format errors below."))
    else:
        student_id_format_form = StudentIDFormatForm(instance=school)

    division_choices = get_division_choices(school)
    student_id_next = {name: 1 for name, _ in division_choices}
    for sequence in school.student_id_sequences.all():
        student_id_next[sequence.division] = sequence.last_number + 1

    custom_by_name = {
        division.name: division
        for division in school.custom_divisions.filter(is_active=True)
    }
    built_in_specs = {
        "Nursery": (
            _("Nursery / Pre-School"),
            student_id_format_form.student_id_nursery_prefix,
            student_id_format_form.student_id_nursery_pattern,
        ),
        "Primary": (
            _("Primary"),
            student_id_format_form.student_id_primary_prefix,
            student_id_format_form.student_id_primary_pattern,
        ),
        "JHS": (
            "JHS",
            student_id_format_form.student_id_jhs_prefix,
            student_id_format_form.student_id_jhs_pattern,
        ),
    }
    division_cards = []
    for name, label in division_choices:
        card = {"name": name, "label": label, "next_number": student_id_next[name]}
        if name in built_in_specs:
            card.update({
                "built_in": True,
                "prefix_field": built_in_specs[name][1],
                "pattern_field": built_in_specs[name][2],
            })
        elif name in custom_by_name:
            card.update({"built_in": False, "division": custom_by_name[name]})
        division_cards.append(card)

    from result.models import PromotionRequest
    pending_count = PromotionRequest.objects.filter(school=school, status='PENDING').count()
    return render(request, 'school/school_settings.html', {
        'active_tab': 'student_ids',
        'student_id_format_form': student_id_format_form,
        'student_id_next': student_id_next,
        'division_cards': division_cards,
        'school_code': f"S{school.pk}",
        'school': school,
        'pending_count': pending_count,
        'title': _('School Settings — Student ID Formats'),
    })


@_school_admin_required
def school_settings_grading(request):
    """Grade weighting configuration tab."""
    school = request.school
    config, created = GradeWeightConfig.objects.get_or_create(school=school)

    if request.method == 'POST':
        form = GradeWeightForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, _("Grade weights saved."))
            return redirect('school_settings_grading')
        else:
            messages.error(request, _("Weights must sum to exactly 100%."))
    else:
        form = GradeWeightForm(instance=config)

    # Build component pairs for the template with icons
    component_data = [
        (form['use_classwork'],  form['classwork_weight'],  _('Classwork'),     _('Daily class participation and activities'), 'fas fa-edit'),
        (form['use_class_test'], form['class_test_weight'], _('Class Test'),    _('Mid-semester examination or class test'), 'fas fa-vial'),
        (form['use_assignment'], form['assignment_weight'], _('Assignments'),   _('Homework and take-home assignments'), 'fas fa-pencil-ruler'),
        (form['use_attendance'], form['attendance_weight'], _('Attendance'),    _('Student attendance record (% converted to score)'), 'fas fa-user-check'),
        (form['use_project'],    form['project_weight'],    _('Project / Labs'), _('Term project or portfolio submission'), 'fas fa-flask'),
    ]

    from result.models import PromotionRequest
    pending_count = PromotionRequest.objects.filter(school=school, status='PENDING').count()

    return render(request, 'school/school_settings.html', {
        'active_tab': 'grading',
        'form': form,
        'config': config,
        'component_data': component_data,
        'pending_count': pending_count,
        'school': school,
        'title': _('School Settings — Grading'),
    })


@_school_admin_required
def school_settings_promotion(request):
    """Promotion policy configuration tab."""
    school = request.school
    policy, created = PromotionPolicy.objects.get_or_create(school=school)

    if request.method == 'POST':
        form = PromotionPolicyForm(request.POST, instance=policy)
        if form.is_valid():
            form.save()
            messages.success(request, _("Promotion policy saved."))
            return redirect('school_settings_promotion')
        else:
            messages.error(request, _("Please correct the errors below."))
    else:
        form = PromotionPolicyForm(instance=policy)

    from result.models import PromotionRequest
    pending_count = PromotionRequest.objects.filter(school=school, status='PENDING').count()
    pending_requests = PromotionRequest.objects.filter(
        school=school, status='PENDING'
    ).select_related('student__student', 'result', 'requested_by')[:10]

    return render(request, 'school/school_settings.html', {
        'active_tab': 'promotion',
        'form': form,
        'policy': policy,
        'pending_count': pending_count,
        'pending_requests': pending_requests,
        'school': school,
        'title': _('School Settings — Promotion'),
    })


@_school_admin_required
def promotion_requests_list(request):
    """List all promotion exception requests for this school."""
    from result.models import PromotionRequest
    school = request.school
    status_filter = request.GET.get('status', 'PENDING')

    requests_qs = PromotionRequest.objects.filter(school=school).select_related(
        'student__student', 'result', 'requested_by', 'reviewed_by'
    ).order_by('-created_at')

    if status_filter in ('PENDING', 'APPROVED', 'REJECTED'):
        requests_qs = requests_qs.filter(status=status_filter)

    return render(request, 'school/promotion_requests.html', {
        'requests': requests_qs,
        'status_filter': status_filter,
        'title': _('Promotion Requests'),
    })


@_school_admin_required
def promotion_request_review(request, pk):
    """Admin approves or rejects a promotion exception request."""
    from result.models import PromotionRequest
    school = request.school
    promo_request = get_object_or_404(PromotionRequest, pk=pk, school=school)

    if request.method == 'POST':
        action = request.POST.get('action')
        notes = request.POST.get('admin_notes', '')
        if action == 'approve':
            promo_request.approve(request.user, notes)
            messages.success(request, _("Request approved successfully."))
        elif action == 'reject':
            promo_request.reject(request.user, notes)
            messages.warning(request, _("Request rejected."))
        if action in ('approve', 'reject'):
            notify(
                school=school,
                recipient=promo_request.requested_by,
                title=f"Promotion request {promo_request.status.lower()}",
                message=f"The request for {promo_request.student} was {promo_request.status.lower()}.",
                link=reverse('promotion_requests_list'),
                notification_type=(
                    Notification.TYPE_SUCCESS if action == 'approve' else Notification.TYPE_WARNING
                ),
                actor=request.user,
            )
        return redirect('promotion_requests_list')

    return render(request, 'school/promotion_request_detail.html', {
        'promo_request': promo_request,
        'title': _('Review Promotion Request'),
    })


@login_required
def submit_promotion_request(request, result_pk):
    """Teacher or admin submits an exception promotion request for a student."""
    from result.models import Result, PromotionRequest
    if not (request.user.is_lecturer or request.user.is_school_admin or request.user.is_superuser):
        messages.error(request, _("Only teachers and admins can submit promotion requests."))
        return redirect('dashboard')

    result = get_object_or_404(Result, pk=result_pk, school=request.school)
    student = result.student

    try:
        policy = request.school.promotion_policy
        if not policy.allow_teacher_requests and not (request.user.is_school_admin or request.user.is_superuser):
            messages.error(request, _("Teacher promotion requests are not enabled for this school."))
            return redirect('dashboard')
    except Exception:
        pass

    if request.method == 'POST':
        request_type = request.POST.get('request_type', 'PROMOTE')
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, _("A reason is required."))
        else:
            existing = PromotionRequest.objects.filter(
                student=student, result=result, status='PENDING'
            ).first()
            if existing:
                messages.warning(request, _("A pending request already exists for this student."))
            else:
                promo_request = PromotionRequest.objects.create(
                    student=student,
                    result=result,
                    request_type=request_type,
                    requested_by=request.user,
                    reason=reason,
                    school=request.school,
                )
                notify_admins(
                    request.school,
                    title="Promotion request needs review",
                    message=f"{request.user.get_full_name} requested a promotion decision for {student}.",
                    link=reverse('promotion_request_review', args=[promo_request.pk]),
                    actor=request.user,
                )
                messages.success(request, _("Promotion request submitted. Awaiting admin review."))
                return redirect('dashboard')

    return render(request, 'school/promotion_request_submit.html', {
        'student': student,
        'result': result,
        'title': _('Submit Promotion Request'),
    })


@_school_admin_required
def run_promotion_engine(request):
    """Admin triggers bulk auto-promotion for all pending results in current term."""
    from result.models import Result
    from core.models import Term

    school = request.school
    if request.method != 'POST':
        return redirect('school_settings_promotion')

    try:
        policy = school.promotion_policy
    except PromotionPolicy.DoesNotExist:
        messages.error(request, _("No promotion policy configured. Set one up first."))
        return redirect('school_settings_promotion')

    current_term = Term.objects.filter(school=school, is_current_term=True).first()
    if not current_term:
        messages.error(request, _("No active term. Set a current term first."))
        return redirect('school_settings_promotion')

    results = Result.objects.filter(
        school=school,
        term=current_term.term,
        promotion_status='PENDING'
    )

    auto_pass = auto_fail = borderline = 0
    for result in results:
        if result.term_average is not None:
            result.auto_evaluate_promotion()
            if result.promotion_status == 'AUTO_PASS':
                auto_pass += 1
            elif result.promotion_status == 'AUTO_FAIL':
                auto_fail += 1
            else:
                borderline += 1

    total = auto_pass + auto_fail + borderline
    messages.success(
        request,
        _(f"Promotion engine complete. {total} students evaluated: "
          f"{auto_pass} passed ✓, {auto_fail} failed ✗, {borderline} borderline ◆")
    )
    return redirect('promotion_requests_list')
