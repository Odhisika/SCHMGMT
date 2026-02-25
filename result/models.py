from decimal import Decimal
from django.conf import settings

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from accounts.models import Student
from core.models import Term
from course.models import Course

# Ghana Education Service Grading Scale (1-9)
GRADE_1 = "1"
GRADE_2 = "2"
GRADE_3 = "3"
GRADE_4 = "4"
GRADE_5 = "5"
GRADE_6 = "6"
GRADE_7 = "7"
GRADE_8 = "8"
GRADE_9 = "9"

GHANA_GRADE_CHOICES = (
    (GRADE_1, "1 - Highest (80-100)"),
    (GRADE_2, "2 - Higher (75-79)"),
    (GRADE_3, "3 - High (70-74)"),
    (GRADE_4, "4 - High Average (65-69)"),
    (GRADE_5, "5 - Average (60-64)"),
    (GRADE_6, "6 - Low Average (55-59)"),
    (GRADE_7, "7 - Lower (50-54)"),
    (GRADE_8, "8 - Low (45-49)"),
    (GRADE_9, "9 - Lowest (0-44)"),
)

# Grade boundaries for Ghana system
GHANA_GRADE_BOUNDARIES = [
    (80, GRADE_1),
    (75, GRADE_2),
    (70, GRADE_3),
    (65, GRADE_4),
    (60, GRADE_5),
    (55, GRADE_6),
    (50, GRADE_7),
    (45, GRADE_8),
    (0, GRADE_9),
]

EXCELLENT = "Excellent"
VERY_GOOD = "Very Good"
GOOD = "Good"
CREDIT = "Credit"
PASS = "Pass"
FAIL = "Fail"

PERFORMANCE_COMMENT = (
    (EXCELLENT, "Excellent"),
    (VERY_GOOD, "Very Good"),
    (GOOD, "Good"),
    (CREDIT, "Credit"),
    (PASS, "Pass"),
    (FAIL, "Fail"),
)

# Promotion Status choices
PROMOTION_STATUS_CHOICES = (
    ('AUTO_PASS', _('Auto Passed')),
    ('AUTO_FAIL', _('Auto Failed')),
    ('BORDERLINE', _('Borderline (Needs Review)')),
    ('MANUAL_PASS', _('Manually Promoted')),
    ('MANUAL_FAIL', _('Manually Held Back')),
    ('PENDING', _('Pending Evaluation')),
)


class TakenCourse(models.Model):
    """
    Student course/subject enrollment and assessment.
    Assessment weights are now driven by the school's GradeWeightConfig.
    Falls back to Ghana standard 40/60 CA/exam if no config found.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="taken_courses"
    )
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    # --- Assessment components ---
    classwork_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Classwork / participation score (raw, out of 100)")
    )
    midsem_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Class test / mid-semester score (raw, out of 100)")
    )
    quiz_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Quiz scores (legacy, maps to class_test in new system)")
    )
    assignment_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Assignment / homework score (raw, out of 100)")
    )
    attendance_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Attendance percentage converted to a score (0-100)")
    )
    project_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Project score (raw, out of 100)")
    )
    exam_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text=_("End of Term Examination score (raw, out of 100)")
    )

    # --- Computed fields (auto-calculated on save) ---
    class_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        editable=False,
        help_text=_("Weighted continuous assessment total (auto-calculated)")
    )
    total = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"), editable=False
    )
    grade = models.CharField(
        choices=GHANA_GRADE_CHOICES, max_length=2, blank=True, editable=False
    )
    comment = models.CharField(
        choices=PERFORMANCE_COMMENT, max_length=20, blank=True, editable=False
    )
    class_position = models.IntegerField(null=True, blank=True, editable=False)
    teacher_remark = models.TextField(blank=True)

    def get_absolute_url(self):
        return reverse("course_detail", kwargs={"slug": self.course.slug})

    def __str__(self):
        return f"{self.course.title} ({self.course.code})"

    def _get_grade_config(self):
        """Fetch the school's GradeWeightConfig, or None if not configured."""
        try:
            if self.school:
                return self.school.grade_config
        except Exception:
            pass
        return None

    def compute_total(self):
        """
        Compute the total score using the school's GradeWeightConfig.
        Fallback: original Ghana 40/60 formula.
        """
        config = self._get_grade_config()
        if config and config.is_valid_config():
            ca = config.calculate_total(
                classwork=float(self.classwork_score),
                class_test=float(self.midsem_score or self.quiz_score),
                assignment=float(self.assignment_score),
                attendance=float(self.attendance_score),
                project=float(self.project_score),
                exam=float(self.exam_score),
            )
            return Decimal(str(ca))
        else:
            # Legacy Ghana 40/60 fallback
            class_total = self.midsem_score + self.quiz_score + self.assignment_score
            return class_total + self.exam_score

    def get_total(self):
        return self.compute_total()

    def get_grade(self):
        """Assign Ghana grade (1-9) based on total score."""
        total = self.total
        for boundary, grade in GHANA_GRADE_BOUNDARIES:
            if total >= boundary:
                return grade
        return GRADE_9

    def get_comment(self):
        """Performance comment based on grade."""
        grade = self.grade
        if grade in [GRADE_1, GRADE_2]:
            return EXCELLENT
        elif grade in [GRADE_3, GRADE_4]:
            return VERY_GOOD
        elif grade in [GRADE_5, GRADE_6]:
            return GOOD
        elif grade == GRADE_7:
            return CREDIT
        elif grade == GRADE_8:
            return PASS
        else:
            return FAIL

    def save(self, *args, **kwargs):
        if not self.school and self.student:
            self.school = self.student.student.school

        config = self._get_grade_config()
        if config and config.is_valid_config():
            # Modern weighted system
            self.total = Decimal(str(config.calculate_total(
                classwork=float(self.classwork_score),
                class_test=float(self.midsem_score or self.quiz_score),
                assignment=float(self.assignment_score),
                attendance=float(self.attendance_score),
                project=float(self.project_score),
                exam=float(self.exam_score),
            )))
            # class_score = total minus exam contribution
            exam_contribution = Decimal(str((float(self.exam_score) / 100) * config.exam_weight))
            self.class_score = max(Decimal("0.00"), self.total - exam_contribution)
        else:
            # Legacy Ghana 40/60 fallback
            self.class_score = self.midsem_score + self.quiz_score + self.assignment_score
            self.total = self.class_score + self.exam_score

        self.grade = self.get_grade()
        self.comment = self.get_comment()
        super().save(*args, **kwargs)
        self.calculate_class_position()

    def calculate_class_position(self):
        """Calculate student's position in class for this subject."""
        same_course_results = TakenCourse.objects.filter(
            course=self.course,
            student__level=self.student.level,
            student__program=self.student.program,
            school=self.school
        ).order_by('-total')

        position = 1
        for idx, result in enumerate(same_course_results, 1):
            if result.id == self.id:
                position = idx
                break

        if self.class_position != position:
            TakenCourse.objects.filter(id=self.id).update(class_position=position)

    def calculate_term_average(self):
        """Calculate average score across all subjects for current term."""
        current_term = Term.objects.filter(is_current_term=True, school=self.school).first()
        if not current_term:
            return Decimal("0.00")

        taken_courses = TakenCourse.objects.filter(
            student=self.student,
            course__level=self.student.level,
            course__term=current_term.term,
        )

        if taken_courses.count() == 0:
            return Decimal("0.00")

        total_score = sum(tc.total for tc in taken_courses)
        average = total_score / Decimal(taken_courses.count())
        return round(average, 2)


class Result(models.Model):
    """Termly report card results for Ghana education system."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    term_average = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Average score across all subjects"
    )
    overall_position = models.IntegerField(
        null=True, blank=True,
        help_text="Student's position in class"
    )
    term = models.CharField(max_length=100, choices=settings.TERM_CHOICES)
    session = models.CharField(max_length=100, blank=True, null=True)
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES, null=True)

    # Teacher comments
    class_teacher_comment = models.TextField(blank=True)
    head_teacher_comment = models.TextField(blank=True)

    # Promotion status
    promotion_status = models.CharField(
        max_length=20,
        choices=PROMOTION_STATUS_CHOICES,
        default='PENDING',
        verbose_name=_("Promotion Status"),
        help_text=_("Set automatically when promotion engine is run, or manually via requests.")
    )
    promoted = models.BooleanField(
        default=False,
        help_text=_("Legacy field. Derived from promotion_status.")
    )

    # Attendance summary
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    total_attendance_days = models.IntegerField(default=0)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"Result for {self.student} - Term: {self.term}, Level: {self.level}"

    def save(self, *args, **kwargs):
        if not self.school and self.student:
            self.school = self.student.student.school
        # Sync promoted boolean from status
        self.promoted = self.promotion_status in ('AUTO_PASS', 'MANUAL_PASS')
        super().save(*args, **kwargs)
        self.calculate_overall_position()

    def auto_evaluate_promotion(self):
        """
        Evaluate and set promotion_status using school's PromotionPolicy.
        Call this when running the promotion engine.
        """
        if not self.school:
            return
        try:
            policy = self.school.promotion_policy
        except Exception:
            return

        if self.term_average is None:
            self.promotion_status = 'PENDING'
        else:
            self.promotion_status = policy.evaluate(self.term_average)
        self.save(update_fields=['promotion_status', 'promoted'])

    def calculate_overall_position(self):
        """Calculate student's position in class based on term average."""
        results = Result.objects.filter(
            term=self.term,
            session=self.session,
            level=self.level,
            school=self.school
        ).order_by('-term_average')

        position = 1
        for idx, result in enumerate(results, 1):
            if result.id == self.id:
                position = idx
                break

        if self.overall_position != position:
            Result.objects.filter(id=self.id).update(overall_position=position)

    @property
    def attendance_percentage(self):
        if self.total_attendance_days > 0:
            return round((self.days_present / self.total_attendance_days) * 100, 1)
        return 0.0

    @property
    def promotion_status_label(self):
        labels = dict(PROMOTION_STATUS_CHOICES)
        return labels.get(self.promotion_status, self.promotion_status)

    @property
    def promotion_status_color(self):
        colors = {
            'AUTO_PASS': 'success',
            'MANUAL_PASS': 'success',
            'AUTO_FAIL': 'danger',
            'MANUAL_FAIL': 'danger',
            'BORDERLINE': 'warning',
            'PENDING': 'secondary',
        }
        return colors.get(self.promotion_status, 'secondary')


class PromotionRequest(models.Model):
    """
    Exception request to promote (or hold back) a student against auto-evaluation.
    Teachers or admins can submit; only admins can approve/reject.
    """
    STATUS_CHOICES = [
        ('PENDING', _('Pending')),
        ('APPROVED', _('Approved')),
        ('REJECTED', _('Rejected')),
    ]
    REQUEST_TYPE = [
        ('PROMOTE', _('Request Promotion (override FAIL)')),
        ('HOLD_BACK', _('Request Hold-Back (override PASS)')),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='promotion_requests')
    result = models.ForeignKey(Result, on_delete=models.CASCADE, related_name='promotion_requests')
    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE, default='PROMOTE')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='submitted_promotion_requests'
    )
    reason = models.TextField(verbose_name=_("Reason for Request"))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_promotion_requests'
    )
    admin_notes = models.TextField(blank=True, verbose_name=_("Admin Notes"))
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Promotion Request")
        verbose_name_plural = _("Promotion Requests")
        ordering = ['-created_at']
        # One pending request per student per result
        unique_together = ['student', 'result', 'status']

    def __str__(self):
        return f"{self.get_request_type_display()} for {self.student} ({self.status})"

    def approve(self, admin_user, notes=''):
        """Approve this request and update the result's promotion status."""
        self.status = 'APPROVED'
        self.reviewed_by = admin_user
        self.admin_notes = notes
        self.save()
        # Update the result
        new_status = 'MANUAL_PASS' if self.request_type == 'PROMOTE' else 'MANUAL_FAIL'
        self.result.promotion_status = new_status
        self.result.save(update_fields=['promotion_status', 'promoted'])

    def reject(self, admin_user, notes=''):
        """Reject this request, leaving the result unchanged."""
        self.status = 'REJECTED'
        self.reviewed_by = admin_user
        self.admin_notes = notes
        self.save()


class BECEMockExam(models.Model):
    """Mock examination session for JHS 3 students."""
    name = models.CharField(max_length=100, help_text="e.g. First Mock, Second Mock")
    year = models.CharField(max_length=4, help_text="Academic year (e.g., 2024)", default="2024")
    date_started = models.DateField()
    date_finished = models.DateField()
    is_active = models.BooleanField(default=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name = _("BECE Mock Exam")
        verbose_name_plural = _("BECE Mock Exams")

    def __str__(self):
        return f"{self.name} - {self.year}"


class BECEMockResult(models.Model):
    """Results for JHS 3 Mock examinations."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="bece_mock_results")
    mock_exam = models.ForeignKey(BECEMockExam, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    grade = models.CharField(max_length=2, choices=GHANA_GRADE_CHOICES, blank=True)
    remarks = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ['student', 'mock_exam', 'course']
        verbose_name = _("BECE Mock Result")
        verbose_name_plural = _("BECE Mock Results")

    def __str__(self):
        return f"{self.student} - {self.course} - {self.score}"

    def save(self, *args, **kwargs):
        score = float(self.score)
        for boundary, grade in GHANA_GRADE_BOUNDARIES:
            if score >= boundary:
                self.grade = grade
                break
        super().save(*args, **kwargs)


class ResultEditRequest(models.Model):
    """
    Request from teacher to alter results after publication.
    Requires admin approval.
    """
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"

    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    )

    TEACHER_REQUEST = "TEACHER_TO_ADMIN"
    ADMIN_REQUEST = "ADMIN_TO_TEACHER"

    REQUEST_TYPE = (
        (TEACHER_REQUEST, "Teacher requests Admin approval"),
        (ADMIN_REQUEST, "Admin requests Teacher approval"),
    )

    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="result_edit_requests")
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="requests_made", null=True)
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE, default=TEACHER_REQUEST)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"Edit Request: {self.course} by {self.teacher} ({self.status})"
