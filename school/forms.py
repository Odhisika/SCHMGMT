from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from .division_utils import get_division_choices
from .models import (
    School, SchoolDivision, SchoolDivisionLevel, GradeWeightConfig,
    PromotionPolicy, STUDENT_ID_PATTERNS, STUDENT_ID_PREFIX_VALIDATOR,
)


class SchoolIdentityForm(forms.ModelForm):
    """Form for school identity and branding — accessible to school admins."""

    class Meta:
        model = School
        fields = [
            'name', 'motto', 'email', 'phone', 'support_email', 'support_phone', 'address', 'website',
            'founded_year', 'logo', 'secondary_logo',
            'primary_color', 'secondary_color', 'accent_color',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'motto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Knowledge is Light'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'support_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'support_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://'}),
            'founded_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1995'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
            'secondary_logo': forms.FileInput(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'accent_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
        }


class SchoolDivisionForm(forms.Form):
    """Add or edit a school-specific division and the classes under it."""

    division_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    name = forms.CharField(
        max_length=25,
        label=_("Division name"),
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("e.g. Creche")}),
    )
    levels = forms.CharField(
        label=_("Classes / levels"),
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        help_text=_("Enter one class per line, for example Creche 1, Creche 2."),
    )
    id_prefix = forms.CharField(
        max_length=12,
        label=_("Student ID prefix"),
        validators=[STUDENT_ID_PREFIX_VALIDATOR],
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("e.g. CRE")}),
    )
    id_pattern = forms.ChoiceField(
        choices=STUDENT_ID_PATTERNS,
        label=_("Student ID format"),
        initial="SCHOOL_DIVISION_YEAR_SEQUENCE",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, school=None, division=None, **kwargs):
        self.school = school
        self.division = division
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if name.lower() in {value.lower() for value, _ in settings.DIVISION_CHOICES}:
            raise ValidationError(_("Nursery, Primary and JHS are already built in."))
        return name

    def clean_levels(self):
        raw = self.cleaned_data.get("levels") or ""
        levels = []
        seen = set()
        built_in = {code.lower() for code, _ in settings.LEVEL_CHOICES}
        for line in raw.splitlines():
            name = line.strip()
            if not name:
                continue
            if len(name) > 25:
                raise ValidationError(_("Class names must be 25 characters or fewer."))
            if name.lower() in built_in:
                raise ValidationError(
                    _("Use a new class name; %(name)s is already a built-in class.")
                    % {"name": name}
                )
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            levels.append(name)
        if not levels:
            raise ValidationError(_("Add at least one class for this division."))
        return levels

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        prefix = (cleaned.get("id_prefix") or "").strip().upper()
        cleaned["id_prefix"] = prefix

        if self.school and name:
            existing = SchoolDivision.objects.filter(school=self.school, name__iexact=name)
            if self.division:
                existing = existing.exclude(pk=self.division.pk)
            if existing.exists():
                self.add_error("name", _("This division already exists for this school."))

        if prefix:
            built_in_prefixes = {"NUR", "PRI", "JHS"}
            taken = set(built_in_prefixes)
            if self.school:
                others = SchoolDivision.objects.filter(school=self.school)
                if self.division:
                    others = others.exclude(pk=self.division.pk)
                taken.update(d.id_prefix.upper() for d in others)
            if prefix in taken:
                self.add_error("id_prefix", _("Use a different ID prefix."))

        levels = cleaned.get("levels") or []
        if self.school and levels:
            conflicts = SchoolDivisionLevel.objects.filter(
                division__school=self.school, name__in=levels
            )
            if self.division:
                conflicts = conflicts.exclude(division=self.division)
            if conflicts.exists():
                self.add_error(
                    "levels",
                    _("A class with one of these names already exists in another division."),
                )

        return cleaned


class SchoolDivisionOrderForm(forms.Form):
    """Arrange built-in and custom divisions for a school."""

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        self.division_keys = [name for name, _ in get_division_choices(school)]

        placements = {}
        if school and getattr(school, "pk", None):
            placements = {p.division: p.order for p in school.division_order.all()}

        for index, name in enumerate(self.division_keys):
            self.fields[f"order_{index}"] = forms.IntegerField(
                label=name,
                min_value=0,
                initial=placements.get(name, index),
                widget=forms.NumberInput(
                    attrs={"class": "form-control", "min": "0", "style": "max-width: 100px;"}
                ),
            )

    @property
    def division_order_fields(self):
        return [
            (name, self[f"order_{index}"])
            for index, name in enumerate(self.division_keys)
        ]

    def clean(self):
        cleaned = super().clean()
        orders = [
            cleaned.get(f"order_{index}")
            for index in range(len(self.division_keys))
        ]
        orders = [order for order in orders if order is not None]
        if len(orders) != len(set(orders)):
            raise ValidationError(_("Give every division a different order number."))
        return cleaned

    def ordered_divisions(self):
        """Return division names sorted by the submitted order numbers."""
        ordered = sorted(
            (
                (self.cleaned_data[f"order_{index}"], index, name)
                for index, name in enumerate(self.division_keys)
            )
        )
        return [name for _, _, name in ordered]


class StudentIDFormatForm(forms.ModelForm):
    """Configure distinct prefixes and layouts for each student division."""

    class Meta:
        model = School
        fields = (
            "student_id_nursery_prefix",
            "student_id_nursery_pattern",
            "student_id_primary_prefix",
            "student_id_primary_pattern",
            "student_id_jhs_prefix",
            "student_id_jhs_pattern",
        )
        labels = {
            "student_id_nursery_prefix": _("Nursery ID prefix"),
            "student_id_nursery_pattern": _("Nursery ID format"),
            "student_id_primary_prefix": _("Primary ID prefix"),
            "student_id_primary_pattern": _("Primary ID format"),
            "student_id_jhs_prefix": _("JHS ID prefix"),
            "student_id_jhs_pattern": _("JHS ID format"),
        }
        help_texts = {
            "student_id_nursery_prefix": _("Use a short, distinct code such as NUR."),
            "student_id_primary_prefix": _("Use a short, distinct code such as PRI."),
            "student_id_jhs_prefix": _("Use a short, distinct code such as JHS."),
        }
        widgets = {
            "student_id_nursery_prefix": forms.TextInput(attrs={"class": "form-control", "maxlength": 12}),
            "student_id_nursery_pattern": forms.Select(attrs={"class": "form-select"}),
            "student_id_primary_prefix": forms.TextInput(attrs={"class": "form-control", "maxlength": 12}),
            "student_id_primary_pattern": forms.Select(attrs={"class": "form-select"}),
            "student_id_jhs_prefix": forms.TextInput(attrs={"class": "form-control", "maxlength": 12}),
            "student_id_jhs_pattern": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned = super().clean()
        prefix_fields = (
            "student_id_nursery_prefix",
            "student_id_primary_prefix",
            "student_id_jhs_prefix",
        )
        for field_name in prefix_fields:
            if cleaned.get(field_name):
                cleaned[field_name] = cleaned[field_name].strip().upper()
        seen = {}
        for field_name in prefix_fields:
            prefix = cleaned.get(field_name)
            if not prefix:
                continue
            if prefix in seen:
                self.add_error(
                    field_name,
                    _("Each division must have a different student ID prefix."),
                )
                self.add_error(
                    seen[prefix],
                    _("Each division must have a different student ID prefix."),
                )
            else:
                seen[prefix] = field_name
        return cleaned


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
            'final_class_completion_term': forms.Select(attrs={'class': 'form-select'}),
            'final_class_requires_pass': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
