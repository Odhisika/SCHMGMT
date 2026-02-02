from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from accounts.models import Student
from course.models import Course
from core.models import Term


PRESENT = "Present"
ABSENT = "Absent"
LATE = "Late"
EXCUSED = "Excused"

ATTENDANCE_STATUS = (
    (PRESENT, _("Present")),
    (ABSENT, _("Absent")),
    (LATE, _("Late")),
    (EXCUSED, _("Excused")),
)


class Attendance(models.Model):
    """Daily attendance records for students"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=ATTENDANCE_STATUS, default=PRESENT)
    subject = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, 
                                help_text="Optional: track attendance per subject")
    remarks = models.TextField(blank=True, help_text="Reason for absence or lateness")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                   null=True, related_name="recorded_attendance")
    created_at = models.DateTimeField(auto_now_add=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        ordering = ['-date', 'student']
        unique_together = ['student', 'date', 'subject', 'school']
        verbose_name = _("Attendance Record")
        verbose_name_plural = _("Attendance Records")
    
    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"


class AttendanceSummary(models.Model):
    """Term attendance summary per student"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_summaries")
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    days_late = models.IntegerField(default=0)
    days_excused = models.IntegerField(default=0)
    total_school_days = models.IntegerField(default=0, help_text="Total school days in term")
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'term', 'school']
        verbose_name = _("Attendance Summary")
        verbose_name_plural = _("Attendance Summaries")
    
    def __str__(self):
        return f"{self.student} - {self.term}"
    
    @property
    def attendance_percentage(self):
        """Calculate attendance percentage"""
        if self.total_school_days > 0:
            return round((self.days_present / self.total_school_days) * 100, 1)
        return 0.0
    
    def update_summary(self):
        """Update summary from attendance records"""
        from django.db.models import Count, Q
        
        # Get attendance records for this term
        records = Attendance.objects.filter(
            student=self.student,
            date__gte=self.term.session.session  # Simplified - should use term dates
        )
        
        # Count by status
        status_counts = records.values('status').annotate(count=Count('id'))
        
        for item in status_counts:
            status = item['status']
            count = item['count']
            
            if status == PRESENT:
                self.days_present = count
            elif status == ABSENT:
                self.days_absent = count
            elif status == LATE:
                self.days_late = count
            elif status == EXCUSED:
                self.days_excused = count
        
        self.save()
