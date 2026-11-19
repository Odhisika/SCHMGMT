from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.contrib.auth.forms import (
    UserCreationForm,
    UserChangeForm,
)
from django.contrib.auth.forms import PasswordResetForm
from django.conf import settings
from course.models import Program
from .models import (
    User, Student, SubClass, Parent, RELATION_SHIP, LEVEL, GENDERS,
    NON_TEACHING_POSITIONS,
)
from .utils import (
    generate_password,
    generate_student_credentials,
    generate_lecturer_credentials,
    generate_parent_credentials,
    generate_admin_credentials,
    send_new_account_email,
    get_division_for_level,
)


# GES-aligned field groups. Keeping these in one place makes it easy to keep
# the student, teacher and non-teaching registration forms consistent.
GES_BIO_FIELDS = (
    "other_names",
    "date_of_birth",
    "place_of_birth",
    "nationality",
    "hometown",
    "region",
    "district",
    "religion",
)
GES_CONTACT_FIELDS = ("gps_address", "alternate_phone")
GES_ID_FIELDS = ("ghana_card_number", "nhis_number")
GES_ADULT_FIELDS = ("marital_status",)
GES_STUDENT_FIELDS = (
    "admission_number",
    "admission_date",
    "previous_school",
    "previous_class",
    "bece_year",
    "bece_index_number",
    "bece_aggregate",
    "birth_certificate_number",
    "boarding_status",
    "guardian_name",
    "guardian_relationship",
    "guardian_phone",
    "guardian_email",
    "guardian_occupation",
    "guardian_address",
    "guardian_ghana_card",
    "second_guardian_name",
    "second_guardian_relationship",
    "second_guardian_phone",
    "second_guardian_occupation",
    "blood_group",
    "medical_conditions",
    "allergies",
    "special_needs",
)
GES_STAFF_STATUTORY_FIELDS = (
    "ssnit_number",
    "tin_number",
    "national_service_number",
)
GES_STAFF_EMPLOYMENT_FIELDS = (
    "staff_id",
    "date_of_first_appointment",
    "date_of_current_appointment",
    "date_employed",
    "employment_type",
    "designation",
    "work_unit",
    "payroll_number",
)
GES_STAFF_QUALIFICATION_FIELDS = (
    "highest_qualification",
    "qualification_institution",
    "qualification_year",
    "professional_qualification",
)
GES_TEACHER_SPECIFIC_FIELDS = (
    "subject_specialization",
    "ntc_license_number",
    "ntc_license_expiry",
)
GES_BANK_FIELDS = (
    "bank_name",
    "bank_branch",
    "bank_account_name",
    "bank_account_number",
)
GES_EMERGENCY_FIELDS = (
    "emergency_contact_name",
    "emergency_contact_relationship",
    "emergency_contact_phone",
    "emergency_contact_address",
)

GES_STUDENT_FORM_FIELDS = (
    GES_BIO_FIELDS
    + GES_CONTACT_FIELDS
    + GES_ID_FIELDS
    + GES_STUDENT_FIELDS
    + GES_EMERGENCY_FIELDS
)
GES_STAFF_FORM_FIELDS = (
    GES_BIO_FIELDS
    + GES_CONTACT_FIELDS
    + GES_ID_FIELDS
    + GES_ADULT_FIELDS
    + GES_STAFF_STATUTORY_FIELDS
    + GES_STAFF_EMPLOYMENT_FIELDS
    + GES_STAFF_QUALIFICATION_FIELDS
    + GES_BANK_FIELDS
    + GES_EMERGENCY_FIELDS
)
GES_TEACHER_FORM_FIELDS = GES_STAFF_FORM_FIELDS + GES_TEACHER_SPECIFIC_FIELDS
GES_NON_TEACHING_FORM_FIELDS = GES_STAFF_FORM_FIELDS
GES_ALL_FIELDS = tuple(
    dict.fromkeys(
        GES_STUDENT_FORM_FIELDS
        + GES_TEACHER_FORM_FIELDS
        + ("picture",)
    )
)


def _apply_bootstrap_widgets(form):
    """Give generated model fields a consistent Bootstrap appearance."""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.HiddenInput):
            continue
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
            continue
        if isinstance(widget, forms.DateInput) and not isinstance(
            widget, forms.DateTimeInput
        ):
            # Use the browser's native date picker so users cannot type an
            # ambiguous date format. This also keeps the value in ISO format
            # for Django's DateField parsing.
            widget.input_type = "date"
            widget.format = "%Y-%m-%d"
        css_classes = widget.attrs.get("class", "")
        if "form-control" not in css_classes and "form-select" not in css_classes:
            bootstrap_class = (
                "form-select"
                if isinstance(widget, (forms.Select, forms.SelectMultiple))
                else "form-control"
            )
            widget.attrs["class"] = f"{css_classes} {bootstrap_class}".strip()


def _disable_password_inputs(form):
    """Issue system-generated temporary passwords for newly created accounts."""
    for name in ("password1", "password2"):
        if name in form.fields:
            form.fields[name].disabled = True
            form.fields[name].required = False


def _make_picture_optional(form):
    """Profile photos are useful but must never block a registration."""
    picture = form.fields.get("picture")
    if picture:
        picture.required = False
        picture.help_text = _(
            "Optional. A default profile photo is used when none is uploaded."
        )


class DivisionLevelSelect(forms.Select):
    """Select widget that tags each class level with its school division."""

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        division = get_division_for_level(value) if value else None
        if division:
            option["attrs"]["data-division"] = division
        return option


class SubClassSelect(forms.Select):
    """Select widget that tags each sub-class option with its class level."""

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        # ModelChoiceIteratorValue exposes the model instance through .instance.
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-level"] = instance.level
        return option


class StaffAddForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        super(StaffAddForm, self).__init__(*args, **kwargs)
        _disable_password_inputs(self)
        _apply_bootstrap_widgets(self)
        _make_picture_optional(self)

    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Username",
        required=False,
    )

    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="First Name",
    )

    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Last Name",
    )

    gender = forms.ChoiceField(
        choices=GENDERS,
        widget=forms.Select(
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
    )

    division = forms.ChoiceField(
        choices=[('', 'Select Division')] + list(settings.DIVISION_CHOICES),
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Division (Nursery, Primary, or JHS)",
        required=True,
        help_text="Teachers can only access classes in their assigned division"
    )

    address = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Residential Address",
    )

    phone = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Mobile No.",
    )

    email = forms.EmailField(
        max_length=254,
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
        label="Email (optional)",
        help_text=_("The account can still be accessed with its username if there is no email address."),
    )

    password1 = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "password",
                "class": "form-control",
            }
        ),
        label="Password",
        required=False,
    )

    password2 = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "password",
                "class": "form-control",
            }
        ),
        label="Password Confirmation",
        required=False,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",) + GES_TEACHER_FORM_FIELDS + ("picture",)

    @transaction.atomic()
    def save(self, commit=True):
        user = super().save(commit=False)
        if self.school:
            user.school = self.school
        user.is_lecturer = True
        user.is_teacher = True  # Set both for backward compatibility
        user.first_name = self.cleaned_data.get("first_name")
        user.last_name = self.cleaned_data.get("last_name")
        user.gender = self.cleaned_data.get("gender")
        user.phone = self.cleaned_data.get("phone")
        user.address = self.cleaned_data.get("address")
        user.email = self.cleaned_data.get("email")
        # The division selection is also the teacher's academic department.
        # Keeping one source of truth avoids asking administrators to enter it twice.
        department_division = self.cleaned_data.get("division")
        department_name = dict(settings.DIVISION_CHOICES).get(department_division)
        if department_name and self.school:
            user.department, _ = Program.objects.get_or_create(
                school=self.school,
                division=department_division,
                is_academic_block=True,
                defaults={"title": department_name},
            )
        else:
            user.department = None
        user.division = department_division

        # Generate a username when one was not supplied, but always make sure
        # the account has a usable password and that the credentials email is
        # sent for every newly created account.
        password = self.cleaned_data.get("password1")
        generated_password = None
        if not user.username:
            user.username, generated_password = generate_lecturer_credentials()
            password = password or generated_password
        if not password:
            password = generate_password()
            generated_password = password
        self.temporary_password = generated_password if not self.cleaned_data.get("password1") else None
        user.must_change_password = bool(self.temporary_password)
        user.set_password(password)

        if commit:
            user.save()
            send_new_account_email(user, password)

        return user


class NonTeachingStaffAddForm(UserCreationForm):
    """Create a school employee account without teaching permissions."""

    username = forms.CharField(
        max_length=30,
        required=False,
        label=_("Username (optional)"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    first_name = forms.CharField(
        max_length=150,
        label=_("First name"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=150,
        label=_("Last name"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        label=_("Email address"),
        max_length=254,
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
        help_text=_("Optional. The staff member can sign in using their username."),
    )
    phone = forms.CharField(
        max_length=60,
        required=False,
        label=_("Phone number"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    address = forms.CharField(
        max_length=255,
        required=False,
        label=_("Residential address"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    gender = forms.ChoiceField(
        choices=[("", _("Select gender"))] + list(GENDERS),
        required=False,
        label=_("Gender"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    non_teaching_position = forms.ChoiceField(
        choices=NON_TEACHING_POSITIONS,
        label=_("Position"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    password1 = forms.CharField(
        required=False,
        label=_("Password (optional)"),
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    password2 = forms.CharField(
        required=False,
        label=_("Confirm password"),
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",) + GES_NON_TEACHING_FORM_FIELDS + ("picture",)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)
        _disable_password_inputs(self)
        _apply_bootstrap_widgets(self)
        _make_picture_optional(self)

    @transaction.atomic()
    def save(self, commit=True):
        user = super().save(commit=False)
        user.school = self.school
        user.is_teacher = False
        user.is_lecturer = False
        user.is_student = False
        user.is_parent = False
        user.is_school_admin = False
        user.is_non_teaching_staff = True
        user.non_teaching_position = self.cleaned_data["non_teaching_position"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data.get("phone", "")
        user.address = self.cleaned_data.get("address", "")
        user.gender = self.cleaned_data.get("gender") or None

        generated_username, generated_password = generate_lecturer_credentials()
        if not user.username:
            user.username = generated_username
        password = self.cleaned_data.get("password1") or generated_password
        self.temporary_password = generated_password if not self.cleaned_data.get("password1") else None
        user.must_change_password = bool(self.temporary_password)
        user.set_password(password)

        if commit:
            user.save()
            send_new_account_email(user, password)
        return user


class SchoolAdminAddForm(UserCreationForm):
    """Create a second (or subsequent) administrator for the current school.

    The school and role are always forced by the form/view, never taken from
    submitted data, so a school admin cannot create accounts for other tenants.
    Passwords are system generated and must be changed at first login.
    """

    username = forms.CharField(
        max_length=30,
        required=False,
        label=_("Username (optional)"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    first_name = forms.CharField(
        max_length=150,
        label=_("First name"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=150,
        label=_("Last name"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        max_length=254,
        required=False,
        label=_("Email address"),
        widget=forms.EmailInput(attrs={"class": "form-control"}),
        help_text=_("Optional. Credentials can also be handed over in person."),
    )
    phone = forms.CharField(
        max_length=60,
        required=False,
        label=_("Phone number"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    password1 = forms.CharField(
        required=False,
        label=_("Temporary password (generated)"),
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    password2 = forms.CharField(
        required=False,
        label=_("Confirm temporary password"),
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)
        _disable_password_inputs(self)
        _apply_bootstrap_widgets(self)

    @transaction.atomic()
    def save(self, commit=True):
        user = super().save(commit=False)
        user.school = self.school
        user.is_school_admin = True
        user.is_staff = True
        # Never let this form create a superuser or combine admin with another
        # role; the account must only have school-administrator privileges.
        user.is_superuser = False
        user.is_student = False
        user.is_teacher = False
        user.is_lecturer = False
        user.is_parent = False
        user.is_non_teaching_staff = False
        user.is_dep_head = False
        user.is_class_teacher = False

        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.email = self.cleaned_data.get("email") or None
        user.phone = self.cleaned_data.get("phone") or None

        generated_username, generated_password = generate_admin_credentials()
        if not user.username:
            user.username = generated_username
        # Password inputs are disabled, so a fresh one-time password is always
        # issued and surfaced through the credential handoff screen.
        self.temporary_password = generated_password
        user.must_change_password = True
        user.set_password(generated_password)

        if commit:
            user.save()
            send_new_account_email(user, generated_password)
        return user


class StudentAddForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super(StudentAddForm, self).__init__(*args, **kwargs)
        if self.school:
            self.fields['program'].queryset = Program.objects.filter(school=self.school)
            self.fields["sub_class"].queryset = SubClass.objects.filter(
                school=self.school, is_active=True
            ).order_by("level", "display_order", "name")

        # Narrow the class list to the chosen division. When the form is
        # submitted without a division we keep every level available and
        # derive the division from the selected class in ``clean``.
        division_value = None
        if self.is_bound:
            division_value = self.data.get("division")
        else:
            division_value = self.initial.get("division")
            if not division_value and self.initial.get("level"):
                division_value = get_division_for_level(self.initial["level"])
                if division_value:
                    self.initial["division"] = division_value
        allowed_levels = settings.DIVISION_LEVEL_MAPPING.get(division_value, [])
        if allowed_levels:
            level_labels = dict(LEVEL)
            self.fields["level"].choices = [("", _("Select level"))] + [
                (level, level_labels.get(level, level)) for level in allowed_levels
            ]

        _disable_password_inputs(self)
        _apply_bootstrap_widgets(self)
        _make_picture_optional(self)

    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={"type": "text", "class": "form-control", "id": "username_id"}
        ),
        label="Username",
        required=False,
    )
    address = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Residential Address",
    )

    phone = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Mobile No.",
    )

    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="First name",
    )

    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Last name",
    )

    gender = forms.ChoiceField(
        choices=GENDERS,
        widget=forms.Select(
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
    )

    division = forms.ChoiceField(
        choices=[("", _("Select division"))] + list(settings.DIVISION_CHOICES),
        required=False,
        label=_("Division / Section"),
        help_text=_(
            "Choose a division to narrow the class list. The division is set "
            "automatically from the class when left blank."
        ),
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
    )

    level = forms.ChoiceField(
        choices=[("", _("Select level"))] + list(LEVEL),
        widget=DivisionLevelSelect(
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
        label=_("Class / Level"),
    )

    sub_class = forms.ModelChoiceField(
        queryset=SubClass.objects.none(),
        required=False,
        label=_("Sub-class / Arm"),
        help_text=_("Optional. Choose the sub-class (for example A or B) for this learner."),
        widget=SubClassSelect(
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
    )

    program = forms.ModelChoiceField(
        queryset=Program.objects.all(),
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Program",
    )

    house = forms.ChoiceField(
        choices=[("", _("Select house (optional)"))] + list(settings.HOUSE_CHOICES),
        required=False,
        label=_("House"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={
                "type": "email",
                "class": "form-control",
            }
        ),
        label="Email Address (optional)",
        max_length=254,
        required=False,
        help_text=_("Optional. The student can sign in using their username."),
    )

    password1 = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "password",
                "class": "form-control",
            }
        ),
        label="Password",
        required=False,
    )

    password2 = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "password",
                "class": "form-control",
            }
        ),
        label="Password Confirmation",
        required=False,
    )

    # def validate_email(self):
    #     email = self.cleaned_data['email']
    #     if User.objects.filter(email__iexact=email, is_active=True).exists():
    #         raise forms.ValidationError("Email has taken, try another email address. ")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",) + GES_STUDENT_FORM_FIELDS + ("picture",)

    def clean(self):
        cleaned = super().clean()
        division = cleaned.get("division")
        level = cleaned.get("level")
        sub_class = cleaned.get("sub_class")
        level_division = get_division_for_level(level) if level else None

        if division and level_division and level_division != division:
            self.add_error(
                "level",
                _("The selected class does not belong to the chosen division."),
            )
        elif not division and level_division:
            cleaned["division"] = level_division

        if sub_class:
            if not level:
                self.add_error(
                    "sub_class",
                    _("Choose the class / level before choosing a sub-class."),
                )
            elif sub_class.level != level:
                self.add_error(
                    "sub_class",
                    _("The selected sub-class does not belong to the chosen class."),
                )
            if self.school and sub_class.school_id != self.school.pk:
                self.add_error(
                    "sub_class",
                    _("The selected sub-class does not belong to this school."),
                )

        return cleaned

    @transaction.atomic()
    def save(self, commit=True):
        user = super().save(commit=False)
        program = self.cleaned_data.get("program")
        school = self.school or (program.school if program else None)
        if school:
            user.school = school
        user.is_student = True
        user.first_name = self.cleaned_data.get("first_name")
        user.last_name = self.cleaned_data.get("last_name")
        user.gender = self.cleaned_data.get("gender")
        user.address = self.cleaned_data.get("address")
        user.phone = self.cleaned_data.get("phone")
        user.address = self.cleaned_data.get("address")
        user.email = self.cleaned_data.get("email")
        user.division = self.cleaned_data.get("division") or get_division_for_level(
            self.cleaned_data.get("level")
        )
        
        # Generate a username when one was not supplied, but always make sure
        # the account has a usable password and that the credentials email is
        # sent for every newly created account.
        password = self.cleaned_data.get("password1")
        generated_password = None
        if not user.username:
            division = get_division_for_level(self.cleaned_data.get("level"))
            user.username, generated_password = generate_student_credentials(
                school=school, division=division
            )
            password = password or generated_password
        if not password:
            password = generate_password()
            generated_password = password
        self.temporary_password = generated_password if not self.cleaned_data.get("password1") else None
        user.must_change_password = bool(self.temporary_password)
        user.set_password(password)

        # GES admission records: use the generated student ID as the admission
        # number when the school does not supply a separate one, and stamp the
        # admission date for new registrations.
        if not user.admission_number:
            user.admission_number = user.username
        if not user.admission_date:
            user.admission_date = timezone.localdate()

        if commit:
            user.save()
            Student.objects.create(
                student=user,
                level=self.cleaned_data.get("level"),
                sub_class=self.cleaned_data.get("sub_class"),
                program=self.cleaned_data.get("program"),
                house=self.cleaned_data.get("house") or None,
            )
            send_new_account_email(user, password)

        return user


class ProfileUpdateForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        self.is_admin = kwargs.pop("is_admin", False)
        self.is_staff_admin = kwargs.pop("is_staff_admin", False)
        super(ProfileUpdateForm, self).__init__(*args, **kwargs)

        instance = self.instance
        is_student = getattr(instance, "is_student", False)
        is_teacher = getattr(instance, "is_teacher", False) or getattr(instance, "is_lecturer", False)
        is_non_teaching = getattr(instance, "is_non_teaching_staff", False)

        hidden_fields = set()
        if is_student:
            hidden_fields.update(GES_ADULT_FIELDS)
            hidden_fields.update(GES_STAFF_STATUTORY_FIELDS)
            hidden_fields.update(GES_STAFF_EMPLOYMENT_FIELDS)
            hidden_fields.update(GES_STAFF_QUALIFICATION_FIELDS)
            hidden_fields.update(GES_TEACHER_SPECIFIC_FIELDS)
            hidden_fields.update(GES_BANK_FIELDS)
            hidden_fields.update(
                {
                    "department",
                    "division",
                    "assigned_level",
                    "is_class_teacher",
                    "non_teaching_position",
                }
            )
        elif is_non_teaching:
            hidden_fields.update(GES_STUDENT_FIELDS)
            hidden_fields.update(GES_TEACHER_SPECIFIC_FIELDS)
            hidden_fields.update(
                {"department", "division", "assigned_level", "is_class_teacher"}
            )
        elif is_teacher:
            hidden_fields.update(GES_STUDENT_FIELDS)
            hidden_fields.update({"non_teaching_position"})
        else:
            # School administrators, parents and other account types only need
            # their own bio-data, contact and emergency details here.
            hidden_fields.update(GES_STUDENT_FIELDS)
            hidden_fields.update(GES_STAFF_STATUTORY_FIELDS)
            hidden_fields.update(GES_STAFF_EMPLOYMENT_FIELDS)
            hidden_fields.update(GES_STAFF_QUALIFICATION_FIELDS)
            hidden_fields.update(GES_TEACHER_SPECIFIC_FIELDS)
            hidden_fields.update(GES_BANK_FIELDS)
            hidden_fields.update(
                {
                    "department",
                    "division",
                    "assigned_level",
                    "is_class_teacher",
                    "non_teaching_position",
                }
            )

        for field_name in hidden_fields:
            self.fields.pop(field_name, None)

        # A teacher's academic block is derived from their selected division.
        # Showing both fields makes transfers ambiguous and can block a change
        # when the old department no longer matches the new division.
        if is_teacher and self.is_staff_admin:
            self.fields.pop("department", None)

        if not self.is_staff_admin:
            for field_name in ("division", "assigned_level", "is_class_teacher"):
                self.fields.pop(field_name, None)

        if self.school and "department" in self.fields:
            self.fields["department"].queryset = Program.objects.filter(
                school=self.school
            )

        # Students can have their class/level, programme and house corrected by
        # an administrator from the same form.
        if is_student and self.is_admin:
            self.fields["level"] = forms.ChoiceField(
                choices=[("", _("Select level"))] + list(LEVEL),
                required=False,
                label=_("Class / Level"),
                widget=forms.Select(attrs={"class": "form-select"}),
            )
            program_qs = Program.objects.all()
            if self.school:
                program_qs = program_qs.filter(school=self.school)
            self.fields["program"] = forms.ModelChoiceField(
                queryset=program_qs,
                required=False,
                label=_("Programme"),
                widget=forms.Select(attrs={"class": "form-select"}),
            )
            self.fields["house"] = forms.ChoiceField(
                choices=[("", _("Select house (optional)"))] + list(settings.HOUSE_CHOICES),
                required=False,
                label=_("House"),
                widget=forms.Select(attrs={"class": "form-select"}),
            )
            sub_class_qs = SubClass.objects.none()
            if self.school:
                sub_class_qs = SubClass.objects.filter(
                    school=self.school, is_active=True
                ).order_by("level", "display_order", "name")
            self.fields["sub_class"] = forms.ModelChoiceField(
                queryset=sub_class_qs,
                required=False,
                label=_("Sub-class / Arm"),
                help_text=_(
                    "Optional. Choose the sub-class (for example A or B) for this learner."
                ),
                widget=SubClassSelect(attrs={"class": "form-select"}),
            )
            try:
                student = instance.student
            except Student.DoesNotExist:
                student = None
            if student:
                self.fields["level"].initial = student.level
                self.fields["program"].initial = student.program_id
                self.fields["house"].initial = student.house
                self.fields["sub_class"].initial = student.sub_class_id

        # Restrict fields for non-admin users
        if not self.is_admin:
            restricted_fields = [
                "first_name", "last_name", "gender", "email", 
                "phone", "address", "department", "division",
                "assigned_level", "is_class_teacher",
                # Statutory and bank details should only be changed by an
                # administrator.
                "staff_id", "ssnit_number", "tin_number", "payroll_number",
                "date_of_first_appointment", "date_of_current_appointment",
                "date_employed", "employment_type", "designation",
                "bank_name", "bank_branch", "bank_account_name",
                "bank_account_number", "ntc_license_number", "ntc_license_expiry",
                "national_service_number",
            ]
            for field_name in restricted_fields:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True
                    # Disabled fields are re-populated from the instance. They
                    # must not stay required when the instance value is blank,
                    # otherwise the form can never validate for such users.
                    self.fields[field_name].required = False
                    self.fields[field_name].help_text = _("This field can only be updated by an administrator.")

        _apply_bootstrap_widgets(self)
        _make_picture_optional(self)

    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={
                "type": "email",
                "class": "form-control",
            }
        ),
        label="Email Address",
    )

    first_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="First Name",
    )

    last_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Last Name",
    )

    gender = forms.CharField(
        widget=forms.Select(
            choices=GENDERS,
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
    )

    phone = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Phone No.",
    )

    address = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Address / city",
    )

    department = forms.ModelChoiceField(
        queryset=Program.objects.all(),
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Department / Section",
        required=False,
    )

    division = forms.ChoiceField(
        choices=[("", _("Select Division"))] + list(settings.DIVISION_CHOICES),
        widget=forms.Select(attrs={"class": "form-control"}),
        required=False,
        label=_("Division"),
    )

    assigned_level = forms.ChoiceField(
        choices=[("", _("No class assigned"))] + list(LEVEL),
        widget=forms.Select(attrs={"class": "form-control"}),
        required=False,
        label=_("Assigned Class"),
        help_text=_("Set the class this teacher is responsible for."),
    )

    is_class_teacher = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label=_("Class Teacher"),
    )

    def clean(self):
        cleaned = super().clean()
        division = cleaned.get("division")
        assigned_level = cleaned.get("assigned_level")
        department = cleaned.get("department")

        if self.is_admin and self.is_staff_admin:
            if assigned_level and not division:
                self.add_error("division", _("Choose a division for the assigned class."))
            if assigned_level and division:
                valid_levels = settings.DIVISION_LEVEL_MAPPING.get(division, [])
                if assigned_level not in valid_levels:
                    self.add_error("assigned_level", _("Choose a class within the selected division."))

            if cleaned.get("is_class_teacher") and not assigned_level:
                self.add_error("assigned_level", _("Assign a class before marking this teacher as a class teacher."))

            if department and division and department.division and department.division != division:
                self.add_error("department", _("The department must belong to the selected division."))

        if self.is_admin and getattr(self.instance, "is_student", False):
            level = cleaned.get("level")
            sub_class = cleaned.get("sub_class")
            if sub_class:
                if not level:
                    self.add_error(
                        "sub_class",
                        _("Choose the class / level before choosing a sub-class."),
                    )
                elif sub_class.level != level:
                    self.add_error(
                        "sub_class",
                        _("The selected sub-class does not belong to the chosen class."),
                    )
                if self.school and sub_class.school_id != self.school.pk:
                    self.add_error(
                        "sub_class",
                        _("The selected sub-class does not belong to this school."),
                    )
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=commit)

        if commit and (getattr(user, "is_teacher", False) or getattr(user, "is_lecturer", False)) and self.is_admin and self.is_staff_admin:
            division = self.cleaned_data.get("division")
            if division:
                title = dict(settings.DIVISION_CHOICES).get(division)
                user.department, _ = Program.objects.get_or_create(
                    school=self.school or user.school,
                    division=division,
                    is_academic_block=True,
                    defaults={"title": title},
                )
            else:
                user.department = None
            user.division = division or None
            user.assigned_level = self.cleaned_data.get("assigned_level") or None
            user.is_class_teacher = self.cleaned_data.get("is_class_teacher", False)
            user.save(update_fields=["department", "division", "assigned_level", "is_class_teacher"])

        if commit and getattr(user, "is_student", False):
            try:
                student = user.student
            except Student.DoesNotExist:
                student = None
            if student:
                if "level" in self.cleaned_data and "level" in self.data:
                    student.level = self.cleaned_data.get("level") or student.level
                if "program" in self.cleaned_data and "program" in self.data:
                    student.program = self.cleaned_data.get("program") or student.program
                if "house" in self.cleaned_data and "house" in self.data:
                    student.house = self.cleaned_data.get("house") or None
                if "sub_class" in self.cleaned_data and "sub_class" in self.data:
                    student.sub_class = self.cleaned_data.get("sub_class")
                student.save()

        return user

    class Meta:
        model = User
        fields = list(
            dict.fromkeys(
                [
                    "first_name",
                    "last_name",
                    "gender",
                    "email",
                    "phone",
                    "address",
                    "department",
                    "division",
                    "assigned_level",
                    "is_class_teacher",
                    "non_teaching_position",
                    "picture",
                ]
                + list(GES_ALL_FIELDS)
            )
        )


class SubClassForm(forms.ModelForm):
    """Create or edit a single sub-class for a class level."""

    class Meta:
        model = SubClass
        fields = ("name", "capacity", "class_teacher")
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("e.g. A"),
                    "maxlength": 20,
                }
            ),
            "capacity": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "placeholder": _("Optional")}
            ),
            "class_teacher": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        self.level = kwargs.pop("level", None)
        super().__init__(*args, **kwargs)
        if self.school:
            teachers = User.objects.filter(
                school=self.school, is_teacher=True, is_active=True
            )
            if self.level:
                division = get_division_for_level(self.level)
                if division:
                    teachers = teachers.filter(division=division)
            self.fields["class_teacher"].queryset = teachers.order_by(
                "first_name", "last_name"
            )

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError(_("Enter a name for the sub-class."))
        return name

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        capacity = cleaned.get("capacity")
        if capacity is not None and capacity < 1:
            self.add_error("capacity", _("Capacity must be at least 1."))
        if self.school and self.level and name:
            existing = SubClass.objects.filter(
                school=self.school, level=self.level, name__iexact=name
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                self.add_error(
                    "name",
                    _("A sub-class with this name already exists for this class."),
                )
        return cleaned


class BulkSubClassForm(forms.Form):
    """Create several sub-classes at once using letters or numbers."""

    SCHEME_CHOICES = (
        ("letters", _("Letters (A, B, C...)")),
        ("numbers", _("Numbers (1, 2, 3...)")),
    )

    count = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=2,
        label=_("Number of sub-classes to add"),
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 100}),
    )
    scheme = forms.ChoiceField(
        choices=SCHEME_CHOICES,
        initial="letters",
        label=_("Naming style"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    capacity = forms.IntegerField(
        required=False,
        min_value=1,
        label=_("Capacity per sub-class"),
        help_text=_("Optional. Leave blank for no limit."),
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1, "placeholder": _("Optional")}
        ),
    )


class StudentTransferForm(forms.Form):
    """Move a learner to a different sub-class, optionally in another class."""

    to_level = forms.ChoiceField(
        choices=LEVEL,
        label=_("New class / level"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    to_sub_class = forms.ModelChoiceField(
        queryset=SubClass.objects.none(),
        label=_("New sub-class / arm"),
        widget=SubClassSelect(attrs={"class": "form-select"}),
    )
    note = forms.CharField(
        required=False,
        label=_("Reason / note"),
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": _("Optional note for the transfer history"),
            }
        ),
    )

    def __init__(self, *args, school=None, student=None, **kwargs):
        self.school = school
        self.student = student
        super().__init__(*args, **kwargs)

        queryset = SubClass.objects.none()
        if school is not None:
            queryset = SubClass.objects.filter(
                school=school, is_active=True
            ).order_by("level", "display_order", "name")
        self.fields["to_sub_class"].queryset = queryset

        if student is not None and not self.is_bound:
            self.fields["to_level"].initial = student.level
            self.fields["to_sub_class"].initial = student.sub_class_id

    def clean(self):
        cleaned = super().clean()
        level = cleaned.get("to_level")
        sub_class = cleaned.get("to_sub_class")

        if sub_class:
            if level and sub_class.level != level:
                self.add_error(
                    "to_sub_class",
                    _("The selected sub-class does not belong to the chosen class."),
                )
            if self.school and sub_class.school_id != self.school.pk:
                self.add_error(
                    "to_sub_class",
                    _("The selected sub-class does not belong to this school."),
                )
            if (
                self.student
                and level == self.student.level
                and sub_class.pk == self.student.sub_class_id
            ):
                self.add_error(
                    "to_sub_class",
                    _("The learner is already in this class and sub-class."),
                )
        return cleaned


class StaffPromotionForm(forms.Form):
    """Assign a non-teaching employee to their new teaching division/class."""

    division = forms.ChoiceField(
        choices=[("", _("Select division"))] + list(settings.DIVISION_CHOICES),
        label=_("Teaching division"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    assigned_level = forms.ChoiceField(
        choices=[("", _("No class assigned"))] + list(LEVEL),
        required=False,
        label=_("Assigned class (optional)"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    is_class_teacher = forms.BooleanField(
        required=False,
        label=_("Class teacher"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        division = cleaned.get("division")
        level = cleaned.get("assigned_level")
        if level and level not in settings.DIVISION_LEVEL_MAPPING.get(division, []):
            self.add_error("assigned_level", _("Choose a class within the selected division."))
        if cleaned.get("is_class_teacher") and not level:
            self.add_error("assigned_level", _("Assign a class before marking this teacher as a class teacher."))
        return cleaned


class ProgramUpdateForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super(ProgramUpdateForm, self).__init__(*args, **kwargs)
        if self.school:
            self.fields['program'].queryset = Program.objects.filter(school=self.school)

    program = forms.ModelChoiceField(
        queryset=Program.objects.all(),
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Program",
    )

    class Meta:
        model = Student
        fields = ["program"]


class EmailValidationOnForgotPassword(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data["email"]
        if not User.objects.filter(email__iexact=email, is_active=True).exists():
            msg = "There is no user registered with the specified E-mail address. "
            self.add_error("email", msg)
            return email


class ParentAddForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super(ParentAddForm, self).__init__(*args, **kwargs)
        _disable_password_inputs(self)
        if self.school:
            self.fields['student'].queryset = Student.objects.filter(student__school=self.school)

    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Username (optional)",
        required=False,
    )
    address = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Address",
    )

    phone = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Mobile No.",
    )

    first_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="First name",
    )

    last_name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Last name",
    )

    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={
                "type": "email",
                "class": "form-control",
            }
        ),
        label="Email Address (optional)",
        required=False,
        help_text=_("Optional. The parent can sign in using their username."),
    )

    student = forms.ModelChoiceField(
        queryset=Student.objects.all(),
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Student",
    )

    relation_ship = forms.CharField(
        widget=forms.Select(
            choices=RELATION_SHIP,
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
    )

    password1 = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "password",
                "class": "form-control",
            }
        ),
        label="Password (optional; leave blank to generate temporary credentials)",
        required=False,
    )

    password2 = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "password",
                "class": "form-control",
            }
        ),
        label="Password Confirmation",
        required=False,
    )

    # def validate_email(self):
    #     email = self.cleaned_data['email']
    #     if User.objects.filter(email__iexact=email, is_active=True).exists():
    #         raise forms.ValidationError("Email has taken, try another email address. ")

    class Meta(UserCreationForm.Meta):
        model = User

    @transaction.atomic()
    def save(self):
        user = super().save(commit=False)
        if self.school:
            user.school = self.school
        user.is_parent = True
        user.first_name = self.cleaned_data.get("first_name")
        user.last_name = self.cleaned_data.get("last_name")
        user.address = self.cleaned_data.get("address")
        user.phone = self.cleaned_data.get("phone")
        user.email = self.cleaned_data.get("email")
        provided_password = self.cleaned_data.get("password1")
        if not user.username:
            user.username, generated_password = generate_parent_credentials()
        else:
            generated_password = generate_password()
        password = provided_password or generated_password
        self.temporary_password = generated_password if not provided_password else None
        user.must_change_password = bool(self.temporary_password)
        user.set_password(password)
        user.save()
        parent = Parent.objects.create(
            user=user,
            student=self.cleaned_data.get("student"),
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            email=user.email,
            relation_ship=self.cleaned_data.get("relation_ship"),
        )
        if user.email:
            send_new_account_email(user, password)
        return parent
