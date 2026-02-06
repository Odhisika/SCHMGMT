from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from accounts.models import Student
from core.models import Term


class AttendanceSession(models.Model):
    """Daily attendance session for a class/level"""
    school = models.ForeignKey('school.School', on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES)
    date = models.DateField()
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='marked_attendance_sessions'
    )
    marked_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, help_text=_("General notes for this session"))
    
    class Meta:
        unique_together = ['school', 'level', 'date']
        ordering = ['-date', 'level']
        verbose_name = _("Attendance Session")
        verbose_name_plural = _("Attendance Sessions")
    
    def __str__(self):
        return f"{self.get_level_display()} - {self.date}"
    
    @property
    def total_students(self):
        return self.records.count()
    
    @property
    def present_count(self):
        return self.records.filter(status='PRESENT').count()
    
    @property
    def absent_count(self):
        return self.records.filter(status='ABSENT').count()
    
    @property
    def late_count(self):
        return self.records.filter(status='LATE').count()


class AttendanceRecord(models.Model):
    """Individual student attendance record"""
    STATUS_CHOICES = [
        ('PRESENT', _('Present')),
        ('ABSENT', _('Absent')),
        ('LATE', _('Late')),
        ('EXCUSED', _('Excused')),
    ]
    
    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name='records'
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PRESENT'
    )
    notes = models.TextField(
        blank=True,
        help_text=_("Optional reason for absence/lateness")
    )
    
    class Meta:
        unique_together = ['session', 'student']
        ordering = ['student__student__last_name', 'student__student__first_name']
        verbose_name = _("Attendance Record")
        verbose_name_plural = _("Attendance Records")
    
    def __str__(self):
        return f"{self.student} - {self.session.date} - {self.get_status_display()}"
