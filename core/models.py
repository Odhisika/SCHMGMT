from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.conf import settings


NEWS = _("News")
EVENTS = _("Event")

POST = (
    (NEWS, _("News")),
    (EVENTS, _("Event")),
)

FIRST = _("First")
SECOND = _("Second")
THIRD = _("Third")

TERM = (
    (FIRST, _("First Term")),
    (SECOND, _("Second Term")),
    (THIRD, _("Third Term")),
)



class NewsAndEventsQuerySet(models.query.QuerySet):
    def search(self, query):
        lookups = (
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(posted_as__icontains=query)
        )
        return self.filter(lookups).distinct()


class NewsAndEventsManager(models.Manager):
    def get_queryset(self):
        return NewsAndEventsQuerySet(self.model, using=self._db)

    def all(self):
        return self.get_queryset()

    def get_by_id(self, id):
        qs = self.get_queryset().filter(
            id=id
        )  # NewsAndEvents.objects == self.get_queryset()
        if qs.count() == 1:
            return qs.first()
        return None

    def search(self, query):
        return self.get_queryset().search(query)


class NewsAndEvents(models.Model):
    title = models.CharField(max_length=200, null=True)
    # Long announcements/events must not be silently truncated. ``TextField``
    # also lets the form accept multi-paragraph content without a 200-char cap.
    summary = models.TextField(blank=True, null=True)
    posted_as = models.CharField(choices=POST, max_length=10)
    updated_date = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    upload_time = models.DateTimeField(auto_now=False, auto_now_add=True, null=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    # Targeted Messaging
    target_division = models.CharField(
        max_length=25,
        choices=settings.DIVISION_CHOICES,
        blank=True,
        null=True,
        help_text=_("Send to all users in this division (Leave empty for all divisions)")
    )
    
    TARGET_ROLES = (
        ("ALL", _("All Roles")),
        ("TEACHERS", _("Teachers")),
        ("STUDENTS", _("Students")),
        ("PARENTS", _("Parents")),
        ("SPECIFIC", _("Specific Users")),
    )
    
    target_role = models.CharField(
        max_length=20,
        choices=TARGET_ROLES,
        default="ALL",
        help_text=_("Target a specific role within the division")
    )
    
    specific_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="targeted_posts",
        help_text=_("Send to specific individuals (Overrides division/role if 'Specific Users' role is selected)")
    )

    objects = NewsAndEventsManager()

    def __str__(self):
        return f"{self.title}"


class Term(models.Model):
    term = models.CharField(max_length=10, choices=TERM, blank=True)
    year = models.CharField(max_length=4, help_text="Academic year (e.g., 2024)", default="2024")
    is_current_term = models.BooleanField(default=False, blank=True, null=True)
    start_date = models.DateField(null=True, blank=True, help_text=_("Term start date"))
    end_date = models.DateField(null=True, blank=True, help_text=_("Term end date"))
    next_term_begins = models.DateField(null=True, blank=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    result_released = models.BooleanField(default=False, help_text="Release results to students for this term")

    class Meta:
        unique_together = ["term", "year", "school"]  

    def __str__(self):
        return f"{self.term} - {self.year}"


# Keep Semester as an alias for backward compatibility
Semester = Term


class House(models.Model):
    """School house system for inter-house competitions"""
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20, blank=True)
    points = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        unique_together = ["name", "school"]

    def __str__(self):
        return f"{self.name}"


WEEK_ACTIVITY_TYPES = (
    ("normal_lesson", _("Normal Lesson")),
    ("sports", _("Sports")),
    ("src", _("SRC")),
    ("mid_term", _("Mid-Term Break")),
    ("holiday", _("Holiday")),
)


class TermWeek(models.Model):
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="weeks")
    week_number = models.PositiveIntegerField(verbose_name=_("Week Number"))
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Activity Start Date"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("Activity End Date"))
    activity_type = models.CharField(max_length=20, choices=WEEK_ACTIVITY_TYPES, default="normal_lesson", verbose_name=_("Activity Type"))
    title = models.CharField(max_length=100, blank=True, verbose_name=_("Custom Title"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))

    class Meta:
        ordering = ["week_number"]
        unique_together = ["term", "week_number"]

    def __str__(self):
        return f"{self.term} - Week {self.week_number}: {self.get_activity_type_display()}"


class ActivityLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"[{self.created_at}]{self.message}"


class Notification(models.Model):
    """
    In-app notification shown in the navbar notification center.

    A notification can target a single user (``recipient``) or a whole
    audience inside one school. Audience notifications are shared rows and
    each user tracks their own read state through ``read_by`` so that a
    school admin reading a notification does not mark it as read for other
    admins.
    """

    AUDIENCE_USER = "USER"
    AUDIENCE_ADMIN = "ADMIN"
    AUDIENCE_TEACHER = "TEACHER"
    AUDIENCE_STUDENT = "STUDENT"
    AUDIENCE_PARENT = "PARENT"
    AUDIENCE_ALL = "ALL"

    AUDIENCE_CHOICES = (
        (AUDIENCE_USER, _("Specific user")),
        (AUDIENCE_ADMIN, _("School administrators")),
        (AUDIENCE_TEACHER, _("Teachers")),
        (AUDIENCE_STUDENT, _("Students")),
        (AUDIENCE_PARENT, _("Parents")),
        (AUDIENCE_ALL, _("Everyone")),
    )

    TYPE_INFO = "info"
    TYPE_SUCCESS = "success"
    TYPE_WARNING = "warning"
    TYPE_DANGER = "danger"

    TYPE_CHOICES = (
        (TYPE_INFO, _("Information")),
        (TYPE_SUCCESS, _("Success")),
        (TYPE_WARNING, _("Warning")),
        (TYPE_DANGER, _("Important")),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("Recipient"),
        help_text=_("Set for a personal notification. Leave empty for an audience notification."),
    )
    audience = models.CharField(
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default=AUDIENCE_ALL,
        verbose_name=_("Audience"),
    )
    school = models.ForeignKey(
        "school.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("School"),
    )
    division = models.CharField(
        max_length=25,
        blank=True,
        verbose_name=_("Division"),
        help_text=_("Optional division restriction for this notification."),
    )
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    message = models.TextField(blank=True, verbose_name=_("Message"))
    link = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Link"),
        help_text=_("Optional in-app URL opened when the notification is clicked."),
    )
    notification_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_INFO,
        verbose_name=_("Type"),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
        verbose_name=_("Triggered by"),
    )
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="read_notifications",
        verbose_name=_("Read by"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        indexes = [
            models.Index(fields=["school", "audience"]),
            models.Index(fields=["recipient", "created_at"]),
        ]

    def __str__(self):
        return self.title

    def get_icon(self):
        """Return the Font Awesome icon used by the notification center."""
        return {
            self.TYPE_INFO: "circle-info",
            self.TYPE_SUCCESS: "circle-check",
            self.TYPE_WARNING: "triangle-exclamation",
            self.TYPE_DANGER: "circle-exclamation",
        }.get(self.notification_type, "circle-info")

    def get_color_class(self):
        """Return the Bootstrap colour suffix used by the notification center."""
        return {
            self.TYPE_INFO: "primary",
            self.TYPE_SUCCESS: "success",
            self.TYPE_WARNING: "warning",
            self.TYPE_DANGER: "danger",
        }.get(self.notification_type, "primary")

