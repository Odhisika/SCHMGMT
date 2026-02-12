from .utils import (
    generate_student_credentials,
    generate_lecturer_credentials,
    send_new_account_email,
)


def post_save_account_receiver(instance=None, created=False, *args, **kwargs):
    """
    Send email notification
    """
    # Logic moved to forms/views to ensure username uniqueness before saving
    # and prevent IntegrityError on the first save.
    pass


# ========================================================================
# Student Auto-Enrollment Signal Handlers
# ========================================================================

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


@receiver(post_save, sender='accounts.Student')
def auto_enroll_student_in_courses(sender, instance, created, **kwargs):
    """
    Automatically enroll student in all courses for their assigned level.
    Triggered when:
    - New student is created with a level
    - Existing student's level is updated
    """
    if instance.level:
        from course.models import Course
        from result.models import TakenCourse
        from core.models import ActivityLog
        
        # Get school from student.student.school (OneToOne relationship)
        school = instance.student.school if hasattr(instance, 'student') else None
        
        # Get all courses for this student's level and school
        courses = Course.objects.filter(
            level=instance.level,
            school=school
        )
        
        # Create TakenCourse for each course if it doesn't exist
        enrolled_count = 0
        for course in courses:
            taken_course, created_enrollment = TakenCourse.objects.get_or_create(
                student=instance,
                course=course,
                defaults={'school': school}
            )
            if created_enrollment:
                enrolled_count += 1
        
        # Log enrollment activity
        if enrolled_count > 0:
            try:
                ActivityLog.objects.create(
                    message=f"Student {instance.student.get_full_name} auto-enrolled in {enrolled_count} courses for {instance.level}"
                )
            except Exception:
                pass  # Silently fail if ActivityLog fails


@receiver(pre_save, sender='accounts.Student')
def track_level_changes(sender, instance, **kwargs):
    """
    Track when a student's level changes to trigger re-enrollment.
    Stores the old level in _old_level attribute.
    """
    if instance.pk:  # Only for existing students
        try:
            from .models import Student
            old_instance = Student.objects.get(pk=instance.pk)
            instance._old_level = old_instance.level
        except Student.DoesNotExist:
            instance._old_level = None
    else:
        instance._old_level = None


@receiver(post_save, sender='accounts.Student')
def handle_level_change(sender, instance, **kwargs):
    """
    When a student's level changes, log the change.
    Note: We preserve old course enrollments to maintain grade history.
    New enrollments are created automatically by auto_enroll_student_in_courses.
    """
    old_level = getattr(instance, '_old_level', None)
    
    # If level changed
    if old_level and old_level != instance.level:
        from core.models import ActivityLog
        try:
            ActivityLog.objects.create(
                message=f"Student {instance.student.get_full_name} moved from {old_level} to {instance.level}"
            )
        except Exception:
            pass  # Silently fail if ActivityLog fails
