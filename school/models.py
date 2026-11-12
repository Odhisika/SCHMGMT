from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


STUDENT_ID_PATTERNS = (
    ("DIVISION_SEQUENCE", _("Division prefix + sequence (e.g. NUR-0001)")),
    ("DIVISION_YEAR_SEQUENCE", _("Division prefix + year + sequence (e.g. NUR-2026-0001)")),
    ("SCHOOL_DIVISION_SEQUENCE", _("School code + division prefix + sequence (e.g. S1-NUR-0001)")),
    ("SCHOOL_DIVISION_YEAR_SEQUENCE", _("School code + division prefix + year + sequence (e.g. S1-NUR-2026-0001)")),
)

STUDENT_ID_PREFIX_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9-]{0,11}$",
    message=_("Use 1–12 letters, numbers, or hyphens; start with a letter or number."),
)


class School(models.Model):
    name = models.CharField(max_length=200, unique=True, help_text=_("Name of the school"))
    slug = models.SlugField(max_length=200, unique=True, help_text=_("Unique identifier for the school (subdomain/path)"))
    email = models.EmailField(blank=True, null=True)
    support_email = models.EmailField(blank=True, null=True, verbose_name=_("Support email"))
    support_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name=_("Support phone"))
    logo = models.ImageField(upload_to="school_logos/", blank=True, null=True)
    secondary_logo = models.ImageField(
        upload_to="school_logos/",
        blank=True, null=True,
        verbose_name=_("School Crest"),
        help_text=_("Optional secondary logo / crest")
    )
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    motto = models.CharField(max_length=255, blank=True, null=True, help_text=_("School motto or tagline"))
    founded_year = models.PositiveSmallIntegerField(
        blank=True, null=True,
        help_text=_("Year the school was founded")
    )

    # Student login ID format, configurable independently for each division.
    student_id_nursery_prefix = models.CharField(
        max_length=12, default="NUR", validators=[STUDENT_ID_PREFIX_VALIDATOR]
    )
    student_id_nursery_pattern = models.CharField(
        max_length=40, choices=STUDENT_ID_PATTERNS, default="SCHOOL_DIVISION_YEAR_SEQUENCE"
    )
    student_id_primary_prefix = models.CharField(
        max_length=12, default="PRI", validators=[STUDENT_ID_PREFIX_VALIDATOR]
    )
    student_id_primary_pattern = models.CharField(
        max_length=40, choices=STUDENT_ID_PATTERNS, default="SCHOOL_DIVISION_YEAR_SEQUENCE"
    )
    student_id_jhs_prefix = models.CharField(
        max_length=12, default="JHS", validators=[STUDENT_ID_PREFIX_VALIDATOR]
    )
    student_id_jhs_pattern = models.CharField(
        max_length=40, choices=STUDENT_ID_PATTERNS, default="SCHOOL_DIVISION_YEAR_SEQUENCE"
    )

    # Domain management
    custom_domain = models.URLField(blank=True, null=True, help_text="Custom domain for this school")
    subdomain = models.SlugField(max_length=200, unique=True, help_text="Subdomain for this school")

    # Branding
    primary_color = models.CharField(max_length=7, default='#007bff', help_text="Primary theme color (hex)")
    secondary_color = models.CharField(max_length=7, default='#6c757d', help_text="Secondary theme color (hex)")
    accent_color = models.CharField(max_length=7, default='#ffc107', help_text="Accent / highlight color (hex)")

    # School status
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("School")
        verbose_name_plural = _("Schools")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def _generate_unique_identifier(self, value, field_name):
        base_value = slugify(value) or "school"
        candidate = base_value
        suffix = 2

        queryset = type(self).objects.all()
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)

        while queryset.filter(**{field_name: candidate}).exists():
            candidate = f"{base_value}-{suffix}"
            suffix += 1

        return candidate

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_identifier(self.name, "slug")
        if not self.subdomain:
            self.subdomain = self._generate_unique_identifier(self.slug, "subdomain")
        super().save(*args, **kwargs)

    def get_active_users_count(self):
        return self.users.filter(is_active=True).count()

    def get_student_count(self):
        return self.users.filter(is_student=True, is_active=True).count()

    def get_teacher_count(self):
        return self.users.filter(is_lecturer=True, is_active=True).count()

    def get_admin_count(self):
        return self.users.filter(is_school_admin=True, is_active=True).count()


class StudentIDSequence(models.Model):
    """Persistent independent student ID counter for each school division."""

    DIVISION_CHOICES = (
        ("Nursery", _("Nursery / Pre-School")),
        ("Primary", _("Primary")),
        ("JHS", _("JHS")),
    )

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="student_id_sequences"
    )
    division = models.CharField(max_length=20, choices=DIVISION_CHOICES)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("school", "division"), name="unique_student_id_sequence_per_division"
            )
        ]

    def __str__(self):
        return f"{self.school} — {self.division}: {self.last_number}"


class GradeWeightConfig(models.Model):
    """
    Per-school assessment weight configuration.
    All active component weights must sum to exactly 100.
    """
    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name='grade_config',
        verbose_name=_("School")
    )

    # --- Component toggles ---
    use_classwork = models.BooleanField(default=True, verbose_name=_("Use Classwork"))
    use_class_test = models.BooleanField(default=True, verbose_name=_("Use Class Test / Mid-Sem"))
    use_assignment = models.BooleanField(default=True, verbose_name=_("Use Assignment"))
    use_attendance = models.BooleanField(default=False, verbose_name=_("Use Attendance"))
    use_project = models.BooleanField(default=False, verbose_name=_("Use Project"))

    # --- Component weights (%) ---
    classwork_weight = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Classwork Weight (%)"),
    )
    class_test_weight = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Class Test / Mid-Sem Weight (%)"),
    )
    assignment_weight = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Assignment Weight (%)"),
    )
    attendance_weight = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Attendance Weight (%)"),
    )
    project_weight = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Project Weight (%)"),
    )
    exam_weight = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("End of Term Exam Weight (%)"),
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Grade Weight Configuration")
        verbose_name_plural = _("Grade Weight Configurations")

    def __str__(self):
        return f"Grade Config for {self.school.name}"

    def get_active_weights_total(self):
        """Sum only the weights for enabled components."""
        total = self.exam_weight  # Exam is always active
        if self.use_classwork:
            total += self.classwork_weight
        if self.use_class_test:
            total += self.class_test_weight
        if self.use_assignment:
            total += self.assignment_weight
        if self.use_attendance:
            total += self.attendance_weight
        if self.use_project:
            total += self.project_weight
        return total

    def is_valid_config(self):
        return self.get_active_weights_total() == 100

    def calculate_total(self, classwork=0, class_test=0, assignment=0, attendance=0, project=0, exam=0):
        """
        Calculate a student's weighted total score.
        Each raw score is assumed to be out of 100, then scaled by its weight.
        """
        total = (float(exam) / 100) * self.exam_weight
        if self.use_classwork:
            total += (float(classwork) / 100) * self.classwork_weight
        if self.use_class_test:
            total += (float(class_test) / 100) * self.class_test_weight
        if self.use_assignment:
            total += (float(assignment) / 100) * self.assignment_weight
        if self.use_attendance:
            total += (float(attendance) / 100) * self.attendance_weight
        if self.use_project:
            total += (float(project) / 100) * self.project_weight
        return round(total, 2)


class PromotionPolicy(models.Model):
    """
    School-wide student promotion rules applied at end of term/year.
    """
    school = models.OneToOneField(
        School, on_delete=models.CASCADE, related_name='promotion_policy',
        verbose_name=_("School")
    )
    promotion_cut_off = models.DecimalField(
        max_digits=5, decimal_places=2, default=50.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Promotion Cut-Off (%)"),
        help_text=_("Students scoring >= this average are automatically promoted.")
    )
    failure_cut_off = models.DecimalField(
        max_digits=5, decimal_places=2, default=40.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Failure Cut-Off (%)"),
        help_text=_("Students scoring < this average automatically fail/repeat. "
                    "Students between failure and promotion cut-offs are 'Borderline' (require review).")
    )
    apply_to_all_terms = models.BooleanField(
        default=False,
        verbose_name=_("Apply Each Term"),
        help_text=_("If checked, promotion is evaluated at the end of every term. "
                    "Otherwise only at the end of the academic year (last term).")
    )
    allow_teacher_requests = models.BooleanField(
        default=True,
        verbose_name=_("Allow Teacher Promotion Requests"),
        help_text=_("Teachers can submit promotion exception requests for borderline/failed students.")
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Promotion Policy")
        verbose_name_plural = _("Promotion Policies")

    def __str__(self):
        return f"Promotion Policy for {self.school.name}"

    def evaluate(self, average_score):
        """
        Given a student's average, return their promotion status string.
        Returns: 'AUTO_PASS' | 'AUTO_FAIL' | 'BORDERLINE'
        """
        from decimal import Decimal
        score = Decimal(str(average_score))
        if score >= self.promotion_cut_off:
            return 'AUTO_PASS'
        elif score < self.failure_cut_off:
            return 'AUTO_FAIL'
        else:
            return 'BORDERLINE'
