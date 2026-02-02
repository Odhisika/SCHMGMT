from django import forms
from django.utils.translation import gettext_lazy as _
from .models import School


class SchoolForm(forms.ModelForm):
    """Enhanced form for school management with domain and branding options"""
    
    class Meta:
        model = School
        fields = [
            'name', 'email', 'address', 'phone', 'website', 'logo',
            'is_active', 'custom_domain', 'subdomain', 
            'primary_color', 'secondary_color'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'plan': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'subscription_start': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'subscription_end': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'custom_domain': forms.URLInput(attrs={'class': 'form-control'}),
            'subdomain': forms.TextInput(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'max_students': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_teachers': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make subdomain readonly for existing schools to prevent breaking URLs
        if self.instance and self.instance.pk:
            self.fields['subdomain'].widget.attrs['readonly'] = True


class SchoolOnboardingForm(forms.ModelForm):
    """Simplified form for super admin to create new schools"""
    
    admin_first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text=_("First name of the school administrator")
    )
    
    admin_last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text=_("Last name of the school administrator")
    )
    
    admin_email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        help_text=_("Email address for the school administrator")
    )
    
    admin_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text=_("Phone number for the school administrator")
    )

    class Meta:
        model = School
        fields = ['name', 'email', 'address', 'phone', 'website']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'plan': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class SchoolBrandingForm(forms.ModelForm):
    """Form for updating school branding settings"""
    
    class Meta:
        model = School
        fields = ['logo', 'primary_color', 'secondary_color']
        widgets = {
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
        }


class SchoolStatusForm(forms.ModelForm):
    """Form for managing school status"""
    
    class Meta:
        model = School
        fields = ['is_active']
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

