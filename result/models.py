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




class TakenCourse(models.Model):
    """
    Student course/subject enrollment and assessment.
    Ghana system: 40% continuous assessment + 60% exam = 100%
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="taken_courses"
    )
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    # Ghana assessment structure
    class_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal("0.00"),
        help_text="Continuous Assessment: Max 40 marks (classwork, homework, projects)"
    )
    exam_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal("0.00"),
        help_text="End of Term Examination: Max 60 marks"
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

    def get_total(self):
        """Calculate total score (class + exam)"""
        return Decimal(self.class_score) + Decimal(self.exam_score)

    def get_grade(self):
        """Assign Ghana grade (1-9) based on total score"""
        total = self.total
        for boundary, grade in GHANA_GRADE_BOUNDARIES:
            if total >= boundary:
                return grade
        return GRADE_9

    def get_comment(self):
        """Performance comment based on grade"""
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
        self.total = self.get_total()
        self.grade = self.get_grade()
        self.comment = self.get_comment()
        super().save(*args, **kwargs)
        # Calculate class position after save
        self.calculate_class_position()

    def calculate_class_position(self):
        """Calculate student's position in class for this subject"""
        # Get all students in same class/level taking this course
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
        """Calculate average score across all subjects for current term"""
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
    """Termly report card results for Ghana education system"""
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
    
    # Promotion status (for end of year)
    promoted = models.BooleanField(default=False)
    
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
        super().save(*args, **kwargs)
        self.calculate_overall_position()

    def calculate_overall_position(self):
        """Calculate student's position in class based on term average"""
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


class BECEMockExam(models.Model):
    """Mock examination session for JHS 3 students"""
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
        return f"{self.name} - {self.session}"


class BECEMockResult(models.Model):
    """Results for JHS 3 Mock examinations"""
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
        # Automatically assign grade based on score
        score = float(self.score)
        for boundary, grade in GHANA_GRADE_BOUNDARIES:
            if score >= boundary:
                self.grade = grade
                break
        super().save(*args, **kwargs)

