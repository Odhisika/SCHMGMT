from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.models import ActivityLog
from core.utils import unique_slug_generator


class CourseFile(models.Model):
    """
    Learning resource files (PDFs, documents, etc.) for courses.
    Replaces the old Upload model with enhanced tracking.
    """
    title = models.CharField(max_length=200, verbose_name=_("File Title"))
    course = models.ForeignKey(
        'course.Course',
        on_delete=models.CASCADE,
        related_name='resource_files',
        verbose_name=_("Course")
    )
    file = models.FileField(
        upload_to='course_resources/files/%Y/%m/',
        help_text=_("Valid Files: pdf, docx, doc, xls, xlsx, ppt, pptx, zip, rar, 7zip"),
        validators=[
            FileExtensionValidator([
                "pdf", "docx", "doc", "xls", "xlsx", 
                "ppt", "pptx", "zip", "rar", "7zip"
            ])
        ],
        verbose_name=_("File")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Brief description of this resource")
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_files',
        verbose_name=_("Uploaded By")
    )
    school = models.ForeignKey(
        'school.School',
        on_delete=models.CASCADE,
        verbose_name=_("School")
    )
    downloads = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Download Count")
    )
    updated_date = models.DateTimeField(auto_now=True)
    upload_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-upload_time']
        verbose_name = _("Course File")
        verbose_name_plural = _("Course Files")

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse("resources:file_download", kwargs={
            "course_slug": self.course.slug,
            "file_id": self.pk
        })

    def get_extension_short(self):
        """Get short extension name for icon display"""
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
        # Delete the file from storage
        self.file.delete(save=False)
        super().delete(*args, **kwargs)


class CourseVideo(models.Model):
    """
    Learning resource videos for courses.
    Replaces the old UploadVideo model with enhanced features.
    """
    title = models.CharField(max_length=200, verbose_name=_("Video Title"))
    slug = models.SlugField(unique=True, blank=True)
    course = models.ForeignKey(
        'course.Course',
        on_delete=models.CASCADE,
        related_name='resource_videos',
        verbose_name=_("Course")
    )
    video = models.FileField(
        upload_to='course_resources/videos/%Y/%m/',
        help_text=_("Valid video formats: mp4, mkv, wmv, 3gp, f4v, avi, mp3, webm"),
        validators=[
            FileExtensionValidator([
                "mp4", "mkv", "wmv", "3gp", "f4v", "avi", "mp3", "webm"
            ])
        ],
        verbose_name=_("Video File")
    )
    thumbnail = models.ImageField(
        upload_to='course_resources/thumbnails/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_("Thumbnail"),
        help_text=_("Video thumbnail image (optional)")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Brief description of this video")
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_videos',
        verbose_name=_("Uploaded By")
    )
    school = models.ForeignKey(
        'school.School',
        on_delete=models.CASCADE,
        verbose_name=_("School")
    )
    duration = models.DurationField(
        null=True,
        blank=True,
        verbose_name=_("Duration"),
        help_text=_("Video duration (auto-detected if possible)")
    )
    views = models.PositiveIntegerField(
        default=0,
        verbose_name=_("View Count")
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = _("Course Video")
        verbose_name_plural = _("Course Videos")

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse("resources:video_detail", kwargs={
            "course_slug": self.course.slug,
            "video_slug": self.slug
        })

    def increment_views(self):
        """Increment view counter"""
        self.views += 1
        self.save(update_fields=['views'])

    def delete(self, *args, **kwargs):
        # Delete the video and thumbnail from storage
        self.video.delete(save=False)
        if self.thumbnail:
            self.thumbnail.delete(save=False)
        super().delete(*args, **kwargs)


# Signal handlers for activity logging

@receiver(pre_save, sender=CourseVideo)
def video_pre_save_receiver(sender, instance, **kwargs):
    """Generate unique slug for video"""
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=CourseFile)
def log_file_save(sender, instance, created, **kwargs):
    """Log file upload/update activity"""
    if created:
        message = _(f"File '{instance.title}' uploaded to course '{instance.course}'")
        if instance.uploaded_by:
            message += _(f" by {instance.uploaded_by.get_full_name}")
    else:
        message = _(f"File '{instance.title}' updated in course '{instance.course}'")
    
    try:
        ActivityLog.objects.create(message=message)
    except Exception:
        pass  # Silently fail if ActivityLog fails


@receiver(post_delete, sender=CourseFile)
def log_file_delete(sender, instance, **kwargs):
    """Log file deletion"""
    try:
        ActivityLog.objects.create(
            message=_(f"File '{instance.title}' deleted from course '{instance.course}'")
        )
    except Exception:
        pass


@receiver(post_save, sender=CourseVideo)
def log_video_save(sender, instance, created, **kwargs):
    """Log video upload/update activity"""
    if created:
        message = _(f"Video '{instance.title}' uploaded to course '{instance.course}'")
        if instance.uploaded_by:
            message += _(f" by {instance.uploaded_by.get_full_name}")
    else:
        message = _(f"Video '{instance.title}' updated in course '{instance.course}'")
    
    try:
        ActivityLog.objects.create(message=message)
    except Exception:
        pass


@receiver(post_delete, sender=CourseVideo)
def log_video_delete(sender, instance, **kwargs):
    """Log video deletion"""
    try:
        ActivityLog.objects.create(
            message=_(f"Video '{instance.title}' deleted from course '{instance.course}'")
        )
    except Exception:
        pass
