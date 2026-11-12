from django import forms
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
    User, Student, Parent, RELATION_SHIP, LEVEL, GENDERS,
    NON_TEACHING_POSITIONS,
)
from .utils import (
    generate_password,
    generate_student_credentials,
    generate_lecturer_credentials,
    send_new_account_email,
)


class StaffAddForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        super(StaffAddForm, self).__init__(*args, **kwargs)

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

    gender = forms.CharField(
        widget=forms.Select(
            choices=GENDERS,
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
    )

    department = forms.ChoiceField(
        choices=[('', 'Select Department / Section')] + list(settings.DIVISION_CHOICES),
        widget=forms.Select(
            attrs={"class": "browser-default custom-select form-control"}
        ),
        label="Department / Section (e.g. Primary, JHS)",
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

    email = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control",
            }
        ),
        label="Email",
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

    @transaction.atomic()
    def save(self, commit=True):
        user = super().save(commit=False)
        if self.school:
            user.school = self.school
        user.is_lecturer = True
        user.is_teacher = True  # Set both for backward compatibility
        user.first_name = self.cleaned_data.get("first_name")
        user.last_name = self.cleaned_data.get("last_name")
        user.phone = self.cleaned_data.get("phone")
        user.address = self.cleaned_data.get("address")
        user.email = self.cleaned_data.get("email")
        department_division = self.cleaned_data.get("department")
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
        user.division = self.cleaned_data.get("division")  # Save division

        # Generate a username when one was not supplied, but always make sure
        # the account has a usable password and that the credentials email is
        # sent for every newly created account.
        password = self.cleaned_data.get("password1")
        if not user.username:
            user.username, generated_password = generate_lecturer_credentials()
            password = password or generated_password
        if not password:
            password = generate_password()
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
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    phone = forms.CharField(
        max_length=60,
        required=False,
        label=_("Phone number"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    address = forms.CharField(
        max_length=60,
        required=False,
        label=_("Address"),
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
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        super().__init__(*args, **kwargs)

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
        user.set_password(password)

        if commit:
            user.save()
            send_new_account_email(user, password)
        return user


class NonTeachingStaffUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "first_name", "last_name", "email", "phone", "address", "gender",
            "non_teaching_position",
        )
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "non_teaching_position": forms.Select(attrs={"class": "form-select"}),
        }


class StudentAddForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super(StudentAddForm, self).__init__(*args, **kwargs)
        if self.school:
            self.fields['program'].queryset = Program.objects.filter(school=self.school)

    username = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={"type": "text", "class": "form-control", "id": "username_id"}
        ),
        label="Username",
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

    gender = forms.CharField(
        widget=forms.Select(
            choices=GENDERS,
            attrs={
                "class": "browser-default custom-select form-control",
            },
        ),
    )

    level = forms.CharField(
        widget=forms.Select(
            choices=LEVEL,
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

    email = forms.EmailField(
        widget=forms.TextInput(
            attrs={
                "type": "email",
                "class": "form-control",
            }
        ),
        label="Email Address",
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

    @transaction.atomic()
    def save(self, commit=True):
        user = super().save(commit=False)
        if self.school:
            user.school = self.school
        user.is_student = True
        user.first_name = self.cleaned_data.get("first_name")
        user.last_name = self.cleaned_data.get("last_name")
        user.gender = self.cleaned_data.get("gender")
        user.address = self.cleaned_data.get("address")
        user.phone = self.cleaned_data.get("phone")
        user.address = self.cleaned_data.get("address")
        user.email = self.cleaned_data.get("email")
        
        # Generate a username when one was not supplied, but always make sure
        # the account has a usable password and that the credentials email is
        # sent for every newly created account.
        password = self.cleaned_data.get("password1")
        if not user.username:
            user.username, generated_password = generate_student_credentials()
            password = password or generated_password
        if not password:
            password = generate_password()
        user.set_password(password)

        if commit:
            user.save()
            Student.objects.create(
                student=user,
                level=self.cleaned_data.get("level"),
                program=self.cleaned_data.get("program"),
            )
            send_new_account_email(user, password)

        return user


class ProfileUpdateForm(UserChangeForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop("school", None)
        self.is_admin = kwargs.pop("is_admin", False)
        self.is_staff_admin = kwargs.pop("is_staff_admin", False)
        super(ProfileUpdateForm, self).__init__(*args, **kwargs)

        if not self.is_staff_admin:
            for field_name in ("division", "assigned_level", "is_class_teacher"):
                self.fields.pop(field_name, None)
        
        if self.school:
            self.fields["department"].queryset = Program.objects.filter(
                school=self.school
            )

        # Restrict fields for non-admin users
        if not self.is_admin:
            restricted_fields = [
                "first_name", "last_name", "gender", "email", 
                "phone", "address", "department", "division",
                "assigned_level", "is_class_teacher",
            ]
            for field_name in restricted_fields:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True
                    # Disabled fields are re-populated from the instance. They
                    # must not stay required when the instance value is blank,
                    # otherwise the form can never validate for such users.
                    self.fields[field_name].required = False
                    self.fields[field_name].help_text = _("This field can only be updated by an administrator.")

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
        return cleaned

    class Meta:
        model = User
        fields = [
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
            "picture",
        ]


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
        label="Username",
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
        label="Email Address",
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
        label="Password",
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
        user.save()
        parent = Parent.objects.create(
            user=user,
            student=self.cleaned_data.get("student"),
            relation_ship=self.cleaned_data.get("relation_ship"),
        )
        return parent
        return user
