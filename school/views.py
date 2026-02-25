from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from django.core.mail import send_mail
from django.conf import settings

from .models import School, GradeWeightConfig, PromotionPolicy
from .forms import (
    SchoolForm, SchoolOnboardingForm, SchoolStatusForm,
    SchoolIdentityForm, GradeWeightForm, PromotionPolicyForm,
)
from accounts.models import User


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
                PromotionRequest.objects.create(
                    student=student,
                    result=result,
                    request_type=request_type,
                    requested_by=request.user,
                    reason=reason,
                    school=request.school,
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
