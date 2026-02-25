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
    summary = models.TextField(max_length=200, blank=True, null=True)
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


class ActivityLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"[{self.created_at}]{self.message}"

