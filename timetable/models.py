from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class Period(models.Model):
    """Defines time slots in the school day (e.g., Period 1, Break, Assembly)"""
    
    PERIOD_TYPES = (
        ('LESSON', 'Lesson Period'),
        ('BREAK', 'Break Time'),
        ('ASSEMBLY', 'Assembly'),
        ('MORNING', 'Early Morning Class'),
    )
    
    school = models.ForeignKey('school.School', on_delete=models.CASCADE)
    name = models.CharField(max_length=50, help_text=_("e.g., Period 1, Break, Assembly"))
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES, default='LESSON')
    division = models.CharField(
        max_length=25,
        choices=settings.DIVISION_CHOICES,
        blank=True,
        null=True,
        help_text=_("Academic division this period applies to")
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    order = models.IntegerField(help_text=_("Display order in the day"))
    
    class Meta:
        ordering = ['school', 'division', 'order']
        unique_together = ['school', 'division', 'order']
        verbose_name = _("Period")
        verbose_name_plural = _("Periods")
    
    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"
    
    def clean(self):
        """Validate that end_time is after start_time"""
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError(_("End time must be after start time."))


class TimetableEntry(models.Model):
    """The actual schedule assignments for classes"""
    
    DAYS_OF_WEEK = (
        ('MONDAY', _('Monday')),
        ('TUESDAY', _('Tuesday')),
        ('WEDNESDAY', _('Wednesday')),
        ('THURSDAY', _('Thursday')),
        ('FRIDAY', _('Friday')),
    )
    
    school = models.ForeignKey('school.School', on_delete=models.CASCADE)
    term = models.ForeignKey('core.Term', on_delete=models.CASCADE, help_text=_("Timetable for specific term"))
    
    # Class/Grade
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES, help_text=_("Class level"))
    
    # Timing
    day_of_week = models.CharField(max_length=10, choices=DAYS_OF_WEEK)
    period = models.ForeignKey('Period', on_delete=models.CASCADE)
    
    # Assignment
    subject = models.ForeignKey(
        'course.Course', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        help_text=_("Leave blank for free periods")
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'is_lecturer': True},
        related_name='timetable_entries'
    )
    
    # Optional
    classroom = models.CharField(max_length=50, blank=True, help_text=_("e.g., Room A, Lab"))
    notes = models.TextField(blank=True, help_text=_("Special instructions"))
    
    class Meta:
        unique_together = ['school', 'term', 'level', 'day_of_week', 'period']
        ordering = ['day_of_week', 'period__order']
        verbose_name = _('Timetable Entry')
        verbose_name_plural = _('Timetable Entries')
    
    def __str__(self):
        subject_name = self.subject.title if self.subject else "Free Period"
        return f"{self.get_level_display()} - {self.get_day_of_week_display()} {self.period.name}: {subject_name}"
    
    def clean(self):
        """Validate no teacher conflicts"""
        # Ensure school is set before validation
        if not hasattr(self, 'school') or not self.school_id:
            # If school is not set, we skip this validation because it will be set in the view
            # Standard validation will catch it if it remains null on save
            return

        if self.teacher and self.subject and self.period.period_type == 'LESSON':
            conflicts = TimetableEntry.objects.filter(
                school=self.school,
                term=self.term,
                day_of_week=self.day_of_week,
                period=self.period,
                teacher=self.teacher
            ).exclude(pk=self.pk)
            
            if conflicts.exists():
                conflict = conflicts.first()
                raise ValidationError(
                    _(f"{self.teacher.get_full_name} is already assigned to {conflict.get_level_display()} "
                      f"during {self.get_day_of_week_display()} {self.period.name}")
                )
