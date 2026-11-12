from django.db import models
from django.urls import reverse
from django.contrib.auth.models import AbstractUser, UserManager
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from PIL import Image

from course.models import Program
from .validators import ASCIIUsernameValidator


# Import level choices from settings
from django.conf import settings

LEVEL = settings.LEVEL_CHOICES

FATHER = _("Father")
MOTHER = _("Mother")
BROTHER = _("Brother")
SISTER = _("Sister")
GRAND_MOTHER = _("Grand mother")
GRAND_FATHER = _("Grand father")
OTHER = _("Other")

RELATION_SHIP = (
    (FATHER, _("Father")),
    (MOTHER, _("Mother")),
    (BROTHER, _("Brother")),
    (SISTER, _("Sister")),
    (GRAND_MOTHER, _("Grand mother")),
    (GRAND_FATHER, _("Grand father")),
    (OTHER, _("Other")),
)


class CustomUserManager(UserManager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query is not None:
            or_lookup = (
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
            queryset = queryset.filter(
                or_lookup
            ).distinct()  # distinct() is often necessary with Q lookups
        return queryset

    def get_student_count(self):
        return self.model.objects.filter(is_student=True).count()

    def get_teacher_count(self):
        return self.model.objects.filter(is_teacher=True).count() + self.model.objects.filter(is_lecturer=True).count()

    def get_superuser_count(self):
        return self.model.objects.filter(is_superuser=True).count()


GENDERS = ((_("M"), _("Male")), (_("F"), _("Female")))

GHANA_REGIONS = (
    ("Ahafo", _("Ahafo")),
    ("Ashanti", _("Ashanti")),
    ("Bono", _("Bono")),
    ("Bono East", _("Bono East")),
    ("Central", _("Central")),
    ("Eastern", _("Eastern")),
    ("Greater Accra", _("Greater Accra")),
    ("North East", _("North East")),
    ("Northern", _("Northern")),
    ("Oti", _("Oti")),
    ("Savannah", _("Savannah")),
    ("Upper East", _("Upper East")),
    ("Upper West", _("Upper West")),
    ("Volta", _("Volta")),
    ("Western", _("Western")),
    ("Western North", _("Western North")),
)

MARITAL_STATUS = (
    ("SINGLE", _("Single")),
    ("MARRIED", _("Married")),
    ("DIVORCED", _("Divorced")),
    ("WIDOWED", _("Widowed")),
    ("SEPARATED", _("Separated")),
)

EMPLOYMENT_TYPES = (
    ("PERMANENT", _("Permanent")),
    ("CONTRACT", _("Contract")),
    ("TEMPORARY", _("Temporary")),
    ("NATIONAL_SERVICE", _("National Service")),
    ("VOLUNTEER", _("Volunteer")),
    ("PART_TIME", _("Part-time")),
    ("INTERNSHIP", _("Internship")),
)

QUALIFICATIONS = (
    ("WASSCE", _("WASSCE / SSCE")),
    ("CERTIFICATE", _("Certificate")),
    ("DIPLOMA", _("Diploma")),
    ("HND", _("HND")),
    ("BACHELOR", _("Bachelor's Degree")),
    ("MASTER", _("Master's Degree")),
    ("DOCTORATE", _("Doctorate")),
    ("PROFESSIONAL", _("Professional Certificate")),
    ("OTHER", _("Other")),
)

BLOOD_GROUPS = (
    ("A+", "A+"),
    ("A-", "A-"),
    ("B+", "B+"),
    ("B-", "B-"),
    ("AB+", "AB+"),
    ("AB-", "AB-"),
    ("O+", "O+"),
    ("O-", "O-"),
)

BOARDING_STATUS = (
    ("DAY", _("Day")),
    ("BOARDING", _("Boarding")),
)

NON_TEACHING_POSITIONS = (
    ("CLEANER", _("Cleaner")),
    ("DRIVER", _("Driver")),
    ("CANTEEN", _("Canteen Staff")),
    ("SECURITY", _("Security")),
    ("LIBRARIAN", _("Librarian")),
    ("MAINTENANCE", _("Maintenance")),
    ("OTHER", _("Other Staff")),
)


class User(AbstractUser):
    must_change_password = models.BooleanField(
        default=False,
        help_text=_("Require the user to replace a temporary password at next login."),
    )
    is_student = models.BooleanField(default=False)
    is_teacher = models.BooleanField(default=False)
    is_lecturer = models.BooleanField(default=False)  # Keep for backward compatibility
    is_parent = models.BooleanField(default=False)
    is_dep_head = models.BooleanField(default=False)
    is_class_teacher = models.BooleanField(default=False)
    is_school_admin = models.BooleanField(default=False)
    is_non_teaching_staff = models.BooleanField(default=False)
    non_teaching_position = models.CharField(
        max_length=30, choices=NON_TEACHING_POSITIONS, blank=True
    )
    gender = models.CharField(max_length=1, choices=GENDERS, blank=True, null=True)
    phone = models.CharField(max_length=60, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    picture = models.ImageField(
        upload_to="profile_pictures/%y/%m/%d/", default="default.png", null=True
    )
    email = models.EmailField(blank=True, null=True)

    # ------------------------------------------------------------------
    # GES-aligned bio-data and contact details
    # ------------------------------------------------------------------
    other_names = models.CharField(
        max_length=150, blank=True, default="", help_text=_("Other names / middle names")
    )
    date_of_birth = models.DateField(null=True, blank=True)
    place_of_birth = models.CharField(max_length=120, blank=True, default="")
    nationality = models.CharField(max_length=60, blank=True, default="Ghanaian")
    hometown = models.CharField(max_length=120, blank=True, default="")
    region = models.CharField(
        max_length=50, choices=GHANA_REGIONS, blank=True, default=""
    )
    district = models.CharField(max_length=120, blank=True, default="")
    religion = models.CharField(max_length=60, blank=True, default="")
    marital_status = models.CharField(
        max_length=20, choices=MARITAL_STATUS, blank=True, default=""
    )
    ghana_card_number = models.CharField(max_length=20, blank=True, default="")
    nhis_number = models.CharField(max_length=30, blank=True, default="")
    gps_address = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text=_("GhanaPost GPS digital address, e.g. GA-123-4567"),
    )
    alternate_phone = models.CharField(max_length=30, blank=True, default="")

    # ------------------------------------------------------------------
    # Statutory / payroll details (teachers and non-teaching staff)
    # ------------------------------------------------------------------
    staff_id = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text=_("GES staff ID or school employee number"),
    )
    ssnit_number = models.CharField(max_length=30, blank=True, default="")
    tin_number = models.CharField(max_length=30, blank=True, default="")
    payroll_number = models.CharField(max_length=30, blank=True, default="")
    national_service_number = models.CharField(max_length=50, blank=True, default="")

    # Employment details
    date_of_first_appointment = models.DateField(null=True, blank=True)
    date_of_current_appointment = models.DateField(null=True, blank=True)
    date_employed = models.DateField(null=True, blank=True)
    employment_type = models.CharField(
        max_length=30, choices=EMPLOYMENT_TYPES, blank=True, default=""
    )
    designation = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=_("Rank, grade or job title"),
    )
    work_unit = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=_("Section, unit or department where the staff member works"),
    )
    subject_specialization = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=_("Subjects or areas the teacher is qualified to teach"),
    )

    # Qualifications and professional licence
    highest_qualification = models.CharField(
        max_length=30, choices=QUALIFICATIONS, blank=True, default=""
    )
    qualification_institution = models.CharField(max_length=200, blank=True, default="")
    qualification_year = models.PositiveSmallIntegerField(null=True, blank=True)
    professional_qualification = models.CharField(max_length=150, blank=True, default="")
    ntc_license_number = models.CharField(max_length=50, blank=True, default="")
    ntc_license_expiry = models.DateField(null=True, blank=True)

    # Bank / payroll account
    bank_name = models.CharField(max_length=120, blank=True, default="")
    bank_branch = models.CharField(max_length=120, blank=True, default="")
    bank_account_name = models.CharField(max_length=150, blank=True, default="")
    bank_account_number = models.CharField(max_length=30, blank=True, default="")

    # ------------------------------------------------------------------
    # Student admission, guardian and health details
    # ------------------------------------------------------------------
    admission_number = models.CharField(max_length=30, blank=True, default="")
    admission_date = models.DateField(null=True, blank=True)
    previous_school = models.CharField(max_length=200, blank=True, default="")
    previous_class = models.CharField(max_length=50, blank=True, default="")
    bece_year = models.PositiveSmallIntegerField(null=True, blank=True)
    bece_index_number = models.CharField(max_length=30, blank=True, default="")
    bece_aggregate = models.CharField(max_length=10, blank=True, default="")
    birth_certificate_number = models.CharField(max_length=30, blank=True, default="")
    boarding_status = models.CharField(
        max_length=10, choices=BOARDING_STATUS, blank=True, default=""
    )

    guardian_name = models.CharField(max_length=150, blank=True, default="")
    guardian_relationship = models.CharField(
        max_length=30, choices=RELATION_SHIP, blank=True, default=""
    )
    guardian_phone = models.CharField(max_length=30, blank=True, default="")
    guardian_email = models.EmailField(blank=True, default="")
    guardian_occupation = models.CharField(max_length=120, blank=True, default="")
    guardian_address = models.CharField(max_length=255, blank=True, default="")
    guardian_ghana_card = models.CharField(max_length=20, blank=True, default="")
    second_guardian_name = models.CharField(max_length=150, blank=True, default="")
    second_guardian_relationship = models.CharField(
        max_length=30, choices=RELATION_SHIP, blank=True, default=""
    )
    second_guardian_phone = models.CharField(max_length=30, blank=True, default="")
    second_guardian_occupation = models.CharField(max_length=120, blank=True, default="")

    blood_group = models.CharField(
        max_length=5, choices=BLOOD_GROUPS, blank=True, default=""
    )
    medical_conditions = models.TextField(blank=True, default="")
    allergies = models.TextField(blank=True, default="")
    special_needs = models.TextField(blank=True, default="")

    # ------------------------------------------------------------------
    # Next of kin / emergency contact (shared by all roles)
    # ------------------------------------------------------------------
    emergency_contact_name = models.CharField(max_length=150, blank=True, default="")
    emergency_contact_relationship = models.CharField(
        max_length=30, choices=RELATION_SHIP, blank=True, default=""
    )
    emergency_contact_phone = models.CharField(max_length=30, blank=True, default="")
    emergency_contact_address = models.CharField(max_length=255, blank=True, default="")

    username_validator = ASCIIUsernameValidator()

    school = models.ForeignKey(
        "school.School", on_delete=models.CASCADE, null=True, blank=True, related_name="users"
    )

    department = models.ForeignKey(
        "course.Program", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff"
    )

    assigned_level = models.CharField(
        max_length=25, 
        choices=LEVEL, 
        blank=True, 
        null=True,
        help_text=_("The class/level this teacher is responsible for (if class teacher)")
    )

    division = models.CharField(
        max_length=25,
        choices=settings.DIVISION_CHOICES,
        blank=True,
        null=True,
        help_text=_("The school division this teacher belongs to (Nursery, Primary, or JHS)")
    )

    objects = CustomUserManager()

    class Meta:
        ordering = ("-date_joined",)

    @property
    def get_full_name(self):
        full_name = self.username
        name_parts = [part for part in (self.first_name, self.other_names, self.last_name) if part]
        if name_parts:
            full_name = " ".join(name_parts)
        return full_name

    def __str__(self):
        return "{} ({})".format(self.username, self.get_full_name)

    @property
    def get_user_role(self):
        if self.is_superuser:
            role = _("Super Admin")
        elif self.is_school_admin:
            role = _("School Admin")
        elif self.is_student:
            role = _("Student")
        elif self.is_non_teaching_staff:
            role = self.get_non_teaching_position_display() or _("Non-teaching Staff")
        elif self.is_teacher or self.is_lecturer:
            if self.is_class_teacher:
                role = _("Class Teacher")
            else:
                role = _("Teacher")
        elif self.is_parent:
            role = _("Parent")
        else:
            role = _("User")

        return role
    
    @property
    def is_school_staff(self):
        return self.is_school_admin or self.is_lecturer or self.is_dep_head or self.is_class_teacher
    
    @property
    def can_manage_school(self):
        return self.is_superuser or self.is_school_admin

    @property
    def can_manage_quizzes(self):
        """Teachers, lecturers and admins can create and manage quizzes."""
        return (
            self.is_superuser
            or self.is_school_admin
            or self.is_lecturer
            or self.is_teacher
        )
    
    def get_division_levels(self):
        """Return all levels in this teacher's division"""
        if not self.division:
            return []
        return settings.DIVISION_LEVEL_MAPPING.get(self.division, [])
    
    def can_access_level(self, level_code):
        """Check if this teacher can access the given level"""
        # Admins can access all levels
        if self.is_superuser or self.is_school_admin:
            return True
        
        # Teachers can only access levels in their division
        if self.is_teacher or self.is_lecturer:
            if not self.division:
                # If no division is set, deny access by default
                return False
            return level_code in self.get_division_levels()
        
        # Other users have no level-based restrictions
        return True

    def get_picture(self):
        try:
            return self.picture.url
        except:
            no_picture = settings.MEDIA_URL + "default.png"
            return no_picture

    def get_absolute_url(self):
        return reverse("profile_single", kwargs={"user_id": self.id})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            img = Image.open(self.picture.path)
            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.picture.path)
        except:
            pass

    def delete(self, *args, **kwargs):
        if self.picture.url != settings.MEDIA_URL + "default.png":
            self.picture.delete()
        super().delete(*args, **kwargs)


class StudentManager(models.Manager):
    def search(self, query=None):
        qs = self.get_queryset()
        if query is not None:
            or_lookup = Q(level__icontains=query) | Q(program__title__icontains=query)
            qs = qs.filter(
                or_lookup
            ).distinct()  # distinct() is often necessary with Q lookups
        return qs


class Student(models.Model):
    student = models.OneToOneField(User, on_delete=models.CASCADE)
    # id_number = models.CharField(max_length=20, unique=True, blank=True)
    level = models.CharField(max_length=25, choices=LEVEL, null=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, null=True)
    house = models.CharField(max_length=20, choices=settings.HOUSE_CHOICES, blank=True, null=True)

    objects = StudentManager()

    class Meta:
        ordering = ("-student__date_joined",)

    def __str__(self):
        return self.student.get_full_name

    @classmethod
    def get_gender_count(cls):
        males_count = Student.objects.filter(student__gender="M").count()
        females_count = Student.objects.filter(student__gender="F").count()

        return {"M": males_count, "F": females_count}

    def get_absolute_url(self):
        return reverse("profile_single", kwargs={"user_id": self.student_id})

    def get_division(self):
        """Derive the school division (Nursery/Primary/JHS) from the level."""
        if not self.level:
            return None
        for division, levels in settings.DIVISION_LEVEL_MAPPING.items():
            if self.level in levels:
                return division
        return None

    def save(self, *args, **kwargs):
        # Keep the linked user's division in sync with the student's level.
        # Views group students by the user's division (e.g. the student list
        # tabs), so a missing division makes students invisible there.
        division = self.get_division()
        user = self.student
        if division and user.division != division:
            user.division = division
            user.save(update_fields=["division"])
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.student.delete()
        super().delete(*args, **kwargs)


class Parent(models.Model):
    """
    Connect student with their parent, parents can
    only view their connected students information
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student = models.OneToOneField(Student, null=True, on_delete=models.SET_NULL)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=60, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # What is the relationship between the student and
    # the parent (i.e. father, mother, brother, sister)
    relation_ship = models.TextField(choices=RELATION_SHIP, blank=True)

    class Meta:
        ordering = ("-user__date_joined",)

    def __str__(self):
        return self.user.username


class PasswordResetAudit(models.Model):
    """Record administrative password resets without retaining credentials."""

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="password_reset_events",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="performed_password_resets",
    )
    school = models.ForeignKey(
        "school.School", on_delete=models.SET_NULL, null=True, blank=True
    )
    target_username = models.CharField(max_length=150)
    performed_by_username = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class DepartmentHead(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Program, on_delete=models.CASCADE, null=True)

    class Meta:
        ordering = ("-user__date_joined",)

    def __str__(self):
        return "{}".format(self.user)
