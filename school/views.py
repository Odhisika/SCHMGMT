from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.decorators import method_decorator

from django.core.mail import send_mail
from django.conf import settings

from .models import School
from .forms import SchoolForm, SchoolOnboardingForm, SchoolStatusForm
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
        # Save the school first
        school = form.save()
        
        # Create school admin user
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
        
        # Send welcome email with credentials
        self.send_welcome_email(school, admin_user, temp_password)
        
        messages.success(
            self.request, 
            f"School '{school.name}' created successfully with admin user '{admin_user.username}'. "
            f"Welcome email sent to {admin_user.email}."
        )
        return super().form_valid(form)
    
    def send_welcome_email(self, school, admin_user, temp_password):
        """Send welcome email to newly created school admin"""
        subject = f"Welcome to SkyLearn - {school.name} Admin Account"
        message = f"""
Dear {admin_user.get_full_name},

Welcome to SkyLearn! Your school '{school.name}' has been successfully registered.

Here are your login credentials:
Username: {admin_user.username}
Temporary Password: {temp_password}

You can access your school's dashboard at: 
http://{school.subdomain}.yourdomain.com

Please login and change your password immediately.

Best regards,
The SkyLearn Team
        """.strip()
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin_user.email],
                fail_silently=False,
            )
        except Exception as e:
            # Log the error but don't fail the request
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
    """Complete school onboarding process with admin creation"""
    if request.method == 'POST':
        form = SchoolOnboardingForm(request.POST)
        if form.is_valid():
            # Save the school
            school = form.save()
            
            # Create school admin user
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
            
            # Send welcome email
            send_welcome_email(school, admin_user, temp_password)
            
            messages.success(
                request,
                f"School '{school.name}' onboarded successfully! "
                f"Admin credentials sent to {admin_user.email}."
            )
            return redirect('school_list')
    else:
        form = SchoolOnboardingForm()
    
    return render(request, 'school/onboard.html', {
        'form': form,
        'title': 'Onboard New School'
    })


def send_welcome_email(school, admin_user, temp_password):
    """Helper function to send welcome email"""
    subject = f"Welcome to SkyLearn - {school.name} Admin Account"
    message = f"""
Dear {admin_user.get_full_name},

Welcome to SkyLearn! Your school '{school.name}' has been successfully registered.

Here are your login credentials:
Username: {admin_user.username}
Temporary Password: {temp_password}

You can access your school's dashboard at: 
http://{school.subdomain}.localhost:8000

Please login immediately and change your password.

Best regards,
The SkyLearn Team
    """.strip()
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [admin_user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Failed to send welcome email: {e}")


@login_required
@user_passes_test(is_superuser)
def school_switch(request, school_slug):
    """Available only in dev/testing to switch context"""
    school = get_object_or_404(School, slug=school_slug)
    request.session['school_slug'] = school.slug
    messages.success(request, f"Switched to {school.name}")
    return redirect("dashboard")
