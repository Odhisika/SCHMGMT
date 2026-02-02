from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from school.models import School

User = get_user_model()


class SchoolCreationForm(forms.ModelForm):
    """Form for creating/editing schools"""
    
    class Meta:
        model = School
        fields = [
            'name', 'email', 'phone', 'address', 'website',
            'subdomain', 'logo', 'primary_color', 'secondary_color', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'School Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'school@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1234567890'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://school.com'}),
            'subdomain': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'schoolname',
                'pattern': '[a-z0-9-]+',
                'title': 'Lowercase letters, numbers, and hyphens only'
            }),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'subdomain': _('Will be used as: subdomain.yourdomain.com'),
        }
    
    def clean_subdomain(self):
        subdomain = self.cleaned_data.get('subdomain', '').lower()
        
        # Reserved subdomains
        reserved = ['www', 'admin', 'superadmin', 'api', 'mail', 'ftp', 'localhost']
        if subdomain in reserved:
            raise forms.ValidationError(_('This subdomain is reserved.'))
        
        # Check if subdomain is already taken (excluding current instance)
        qs = School.objects.filter(subdomain=subdomain)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise forms.ValidationError(_('This subdomain is already taken.'))
        
        return subdomain


class SchoolAdminCreationForm(UserCreationForm):
    """Form for creating school administrators"""
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'admin@example.com'})
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'})
    )
    phone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'})
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control'})
