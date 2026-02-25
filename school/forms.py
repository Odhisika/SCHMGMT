from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .models import School, GradeWeightConfig, PromotionPolicy


class SchoolIdentityForm(forms.ModelForm):
    """Form for school identity and branding — accessible to school admins."""

    class Meta:
        model = School
        fields = [
            'name', 'motto', 'email', 'phone', 'address', 'website',
            'founded_year', 'logo', 'secondary_logo',
            'primary_color', 'secondary_color', 'accent_color',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'motto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Knowledge is Light'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://'}),
            'founded_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1995'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'secondary_logo': forms.FileInput(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'accent_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
        }


class GradeWeightForm(forms.ModelForm):
    """
    Form for school grade weighting configuration.
    Validates that active component weights sum to exactly 100.
    """

    class Meta:
        model = GradeWeightConfig
        exclude = ['school', 'updated_at']
        widgets = {
            'use_classwork': forms.CheckboxInput(attrs={'class': 'form-check-input component-toggle', 'data-target': 'classwork_weight'}),
            'use_class_test': forms.CheckboxInput(attrs={'class': 'form-check-input component-toggle', 'data-target': 'class_test_weight'}),
            'use_assignment': forms.CheckboxInput(attrs={'class': 'form-check-input component-toggle', 'data-target': 'assignment_weight'}),
            'use_attendance': forms.CheckboxInput(attrs={'class': 'form-check-input component-toggle', 'data-target': 'attendance_weight'}),
            'use_project': forms.CheckboxInput(attrs={'class': 'form-check-input component-toggle', 'data-target': 'project_weight'}),
            'classwork_weight': forms.NumberInput(attrs={'class': 'form-control weight-input', 'min': 0, 'max': 100}),
            'class_test_weight': forms.NumberInput(attrs={'class': 'form-control weight-input', 'min': 0, 'max': 100}),
            'assignment_weight': forms.NumberInput(attrs={'class': 'form-control weight-input', 'min': 0, 'max': 100}),
            'attendance_weight': forms.NumberInput(attrs={'class': 'form-control weight-input', 'min': 0, 'max': 100}),
            'project_weight': forms.NumberInput(attrs={'class': 'form-control weight-input', 'min': 0, 'max': 100}),
            'exam_weight': forms.NumberInput(attrs={'class': 'form-control weight-input', 'min': 0, 'max': 100}),
        }

    def clean(self):
        cleaned = super().clean()
        total = cleaned.get('exam_weight', 0)
        if cleaned.get('use_classwork'):
            total += cleaned.get('classwork_weight', 0)
        if cleaned.get('use_class_test'):
            total += cleaned.get('class_test_weight', 0)
        if cleaned.get('use_assignment'):
            total += cleaned.get('assignment_weight', 0)
        if cleaned.get('use_attendance'):
            total += cleaned.get('attendance_weight', 0)
        if cleaned.get('use_project'):
            total += cleaned.get('project_weight', 0)

        if total != 100:
            raise ValidationError(
                _('The weights of all active components must sum to exactly 100%. '
                  f'Current total: {total}%.')
            )
        return cleaned


class PromotionPolicyForm(forms.ModelForm):
    """Form for school-wide promotion cut-off configuration."""

    class Meta:
        model = PromotionPolicy
        exclude = ['school', 'updated_at']
        widgets = {
            'promotion_cut_off': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0, 'max': 100, 'step': '0.5'
            }),
            'failure_cut_off': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0, 'max': 100, 'step': '0.5'
            }),
            'apply_to_all_terms': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_teacher_requests': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        promo = cleaned.get('promotion_cut_off')
        fail = cleaned.get('failure_cut_off')
        if promo is not None and fail is not None:
            if fail >= promo:
                raise ValidationError(
                    _('Failure cut-off must be lower than the promotion cut-off. '
                      f'Got: failure={fail}%, promotion={promo}%.')
                )
        return cleaned


class SchoolForm(forms.ModelForm):
    """Legacy enhanced form for super admin school management."""

    class Meta:
        model = School
        fields = [
            'name', 'email', 'address', 'phone', 'website', 'logo',
            'is_active', 'custom_domain', 'subdomain',
            'primary_color', 'secondary_color',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'custom_domain': forms.URLInput(attrs={'class': 'form-control'}),
            'subdomain': forms.TextInput(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['subdomain'].widget.attrs['readonly'] = True


class SchoolOnboardingForm(forms.ModelForm):
    """Simplified form for super admin to create new schools."""

    admin_first_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'class': 'form-control'}))
    admin_last_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'class': 'form-control'}))
    admin_email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    admin_phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = School
        fields = ['name', 'email', 'address', 'phone', 'website']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'website': forms.URLInput(attrs={'class': 'form-control'}),
        }


class SchoolBrandingForm(forms.ModelForm):
    """Legacy branding form (kept for backward compatibility)."""

    class Meta:
        model = School
        fields = ['logo', 'primary_color', 'secondary_color']
        widgets = {
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
        }


class SchoolStatusForm(forms.ModelForm):
    """Legacy status form."""

    class Meta:
        model = School
        fields = ['is_active']
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
