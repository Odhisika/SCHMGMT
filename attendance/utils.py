from django.utils import timezone
from .models import Attendance, AttendanceSummary, PRESENT
from core.models import Term

def sync_attendance_records(student, school):
    """
    Ensure student has an attendance summary for the current term.
    """
    current_term = Term.objects.filter(is_current_term=True, school=school).first()
    if not current_term:
        return
    
    AttendanceSummary.objects.get_or_create(
        student=student,
        term=current_term,
        school=school
    )

def create_initial_attendance_for_course(student, course, school):
    """
    Optional: Create an initial 'Present' record for a new enrollment? 
    Usually, attendance is marked daily via AttendanceSession.
    For now, we just ensure the summary exists.
    """
    sync_attendance_records(student, school)
