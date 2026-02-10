from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_save, post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.models import ActivityLog, Term
from core.utils import unique_slug_generator

# Keep Semester import for backward compatibility
Semester = Term


class ProgramManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query:
            or_lookup = Q(title__icontains=query) | Q(summary__icontains=query)
            queryset = queryset.filter(or_lookup).distinct()
        return queryset


class Program(models.Model):
    title = models.CharField(max_length=150)
    summary = models.TextField(blank=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    objects = ProgramManager()

    class Meta:
        unique_together = ["title", "school"]

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse("program_detail", kwargs={"pk": self.pk})


@receiver(post_save, sender=Program)
def log_program_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    ActivityLog.objects.create(message=_(f"The program '{instance}' has been {verb}."))


@receiver(post_delete, sender=Program)
def log_program_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"The program '{instance}' has been deleted."))


class CourseManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query:
            or_lookup = (
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(code__icontains=query)
                | Q(slug__icontains=query)
            )
            queryset = queryset.filter(or_lookup).distinct()
        return queryset


class Course(models.Model):
    slug = models.SlugField(unique=True, blank=True)
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=200)
    summary = models.TextField(max_length=200, blank=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES)
    term = models.CharField(choices=settings.TERM_CHOICES, max_length=200)
    is_core_subject = models.BooleanField(default=True, help_text=_("Core subjects are mandatory"))
    is_elective = models.BooleanField(default=False)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        unique_together = ["code", "school"]

    objects = CourseManager()

    def __str__(self):
        return f"{self.title} ({self.code})"

    def get_absolute_url(self):
        return reverse("course_detail", kwargs={"slug": self.slug})

    @property
    def is_current_term(self):
        current_term = Term.objects.filter(is_current_term=True).first()
        return self.term == current_term.term if current_term else False
    
    # Keep for backward compatibility
    @property
    def semester(self):
        return self.term
    
    @property
    def is_current_semester(self):
        return self.is_current_term


@receiver(pre_save, sender=Course)
def course_pre_save_receiver(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=Course)
def log_course_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    ActivityLog.objects.create(message=_(f"The course '{instance}' has been {verb}."))


@receiver(post_delete, sender=Course)
def log_course_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"The course '{instance}' has been deleted."))


class CourseAllocation(models.Model):
    """Allocate courses/subjects to teachers"""
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="allocated_teacher",
    )
    # Keep lecturer field for backward compatibility
    @property
    def lecturer(self):
        return self.teacher
    
    courses = models.ManyToManyField(Course, related_name="allocated_course")

    def __str__(self):
        return self.teacher.get_full_name

    def get_absolute_url(self):
        return reverse("edit_allocated_course", kwargs={"pk": self.pk})


class Upload(models.Model):
    title = models.CharField(max_length=100)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    file = models.FileField(
        upload_to="course_files/",
        help_text=_(
            "Valid Files: pdf, docx, doc, xls, xlsx, ppt, pptx, zip, rar, 7zip"
        ),
        validators=[
            FileExtensionValidator(
                [
                    "pdf",
                    "docx",
                    "doc",
                    "xls",
                    "xlsx",
                    "ppt",
                    "pptx",
                    "zip",
                    "rar",
                    "7zip",
                ]
            )
        ],
    )
    updated_date = models.DateTimeField(auto_now=True)
    upload_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title}"

    def get_extension_short(self):
        ext = self.file.name.split(".")[-1].lower()
        if ext in ("doc", "docx"):
            return "word"
        elif ext == "pdf":
            return "pdf"
        elif ext in ("xls", "xlsx"):
            return "excel"
        elif ext in ("ppt", "pptx"):
            return "powerpoint"
        elif ext in ("zip", "rar", "7zip"):
            return "archive"
        return "file"

    def delete(self, *args, **kwargs):
        self.file.delete(save=False)
        super().delete(*args, **kwargs)


@receiver(post_save, sender=Upload)
def log_upload_save(sender, instance, created, **kwargs):
    if created:
        message = _(
            f"The file '{instance.title}' has been uploaded to the course '{instance.course}'."
        )
    else:
        message = _(
            f"The file '{instance.title}' of the course '{instance.course}' has been updated."
        )
    ActivityLog.objects.create(message=message)


@receiver(post_delete, sender=Upload)
def log_upload_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"The file '{instance.title}' of the course '{instance.course}' has been deleted."
        )
    )


class UploadVideo(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    video = models.FileField(
        upload_to="course_videos/",
        help_text=_("Valid video formats: mp4, mkv, wmv, 3gp, f4v, avi, mp3"),
        validators=[
            FileExtensionValidator(["mp4", "mkv", "wmv", "3gp", "f4v", "avi", "mp3"])
        ],
    )
    summary = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse(
            "video_single", kwargs={"slug": self.course.slug, "video_slug": self.slug}
        )

    def delete(self, *args, **kwargs):
        self.video.delete(save=False)
        super().delete(*args, **kwargs)


@receiver(pre_save, sender=UploadVideo)
def video_pre_save_receiver(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=UploadVideo)
def log_uploadvideo_save(sender, instance, created, **kwargs):
    if created:
        message = _(
            f"The video '{instance.title}' has been uploaded to the course '{instance.course}'."
        )
    else:
        message = _(
            f"The video '{instance.title}' of the course '{instance.course}' has been updated."
        )
    ActivityLog.objects.create(message=message)


@receiver(post_delete, sender=UploadVideo)
def log_uploadvideo_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"The video '{instance.title}' of the course '{instance.course}' has been deleted."
        )
    )


class LessonNote(models.Model):
    """Lesson notes submitted by teachers for admin review"""
    
    STATUS_CHOICES = (
        ('DRAFT', _('Draft')),
        ('SUBMITTED', _('Submitted for Review')),
        ('APPROVED', _('Approved')),
        ('REJECTED', _('Needs Revision')),
    )
    
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_notes',
        verbose_name=_('Teacher')
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        verbose_name=_('Course')
    )
    term = models.ForeignKey(
        'core.Term',
        on_delete=models.CASCADE,
        verbose_name=_('Term')
    )
    week_number = models.PositiveIntegerField(
        verbose_name=_('Week Number'),
        help_text=_('Week number for this lesson (e.g., Week 1, Week 2)')
    )
    title = models.CharField(
        max_length=200,
        verbose_name=_('Lesson Title')
    )
    topic = models.CharField(
        max_length=300,
        verbose_name=_('Topic/Subject Matter')
    )
    objectives = models.TextField(
        verbose_name=_('Learning Objectives'),
        help_text=_('What students should learn/achieve by the end of the lesson')
    )
    content = models.TextField(
        verbose_name=_('Lesson Content'),
        help_text=_('Detailed lesson content and key points to cover')
    )
    methodology = models.TextField(
        verbose_name=_('Teaching Methods'),
        help_text=_('Teaching methods, activities, and instructional strategies')
    )
    assessment = models.TextField(
        blank=True,
        verbose_name=_('Assessment Methods'),
        help_text=_('How student learning will be assessed')
    )
    resources_needed = models.TextField(
        blank=True,
        verbose_name=_('Resources/Materials'),
        help_text=_('Materials, equipment, and resources needed')
    )
    homework = models.TextField(
        blank=True,
        verbose_name=_('Homework/Assignment'),
        help_text=_('Homework or assignments for students')
    )
    
    # File attachments
    attachment = models.FileField(
        upload_to='lesson_notes/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_('Attachment'),
        help_text=_('Optional: Attach supporting documents (PDF, DOCX, DOC)'),
        validators=[
            FileExtensionValidator(['pdf', 'docx', 'doc'])
        ]
    )
    
    # Workflow and approval
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
        verbose_name=_('Status')
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Submitted At')
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_lesson_notes',
        verbose_name=_('Reviewed By')
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Reviewed At')
    )
    admin_comments = models.TextField(
        blank=True,
        verbose_name=_('Admin Comments'),
        help_text=_('Feedback from admin/reviewer')
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )
    
    class Meta:
        verbose_name = _('Lesson Note')
        verbose_name_plural = _('Lesson Notes')
        ordering = ['-created_at']
        unique_together = ['course', 'term', 'week_number', 'teacher']
    
    def __str__(self):
        return f"{self.course.code} - Week {self.week_number} - {self.title}"
    
    def can_edit(self):
        """Check if lesson note can be edited (only drafts and rejected notes)"""
        return self.status in ['DRAFT', 'REJECTED']
    
    def can_submit(self):
        """Check if lesson note can be submitted"""
        return self.status in ['DRAFT', 'REJECTED']
    
    def get_status_display_class(self):
        """Return Bootstrap class for status badge"""
        status_classes = {
            'DRAFT': 'secondary',
            'SUBMITTED': 'info',
            'APPROVED': 'success',
            'REJECTED': 'danger',
        }
        return status_classes.get(self.status, 'secondary')


@receiver(post_save, sender=LessonNote)
def log_lesson_note_save(sender, instance, created, **kwargs):
    if created:
        message = _(
            f"Lesson note '{instance.title}' created by {instance.teacher.get_full_name} "
            f"for {instance.course.title}."
        )
    else:
        message = _(
            f"Lesson note '{instance.title}' for {instance.course.title} has been updated."
        )
    ActivityLog.objects.create(message=message)


@receiver(post_delete, sender=LessonNote)
def log_lesson_note_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"Lesson note '{instance.title}' for {instance.course.title} has been deleted."
        )
    )


class CourseOffer(models.Model):
    """NOTE: Only department head can offer semester courses"""

    dep_head = models.ForeignKey("accounts.DepartmentHead", on_delete=models.CASCADE)

    def __str__(self):
        return str(self.dep_head)
