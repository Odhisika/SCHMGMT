from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from accounts.models import Student, User
from course.models import Course, CourseAllocation
from result.models import TakenCourse
from core.models import Term, ActivityLog
from attendance.utils import sync_attendance_records


@receiver(post_save, sender=Student)
def auto_enroll_student_in_courses(sender, instance, created, **kwargs):
    """
    Automatically enroll students in all core courses for their level/program
    when they are created or when their level/program changes.
    """
    # Skip if this is being loaded from a fixture
    if kwargs.get('raw', False):
        return
    
    # Get the student's school
    school = instance.student.school
    if not school:
        return
    
    # Get current term
    current_term = Term.objects.filter(is_current_term=True, school=school).first()
    if not current_term:
        return
    
    # Find all core courses matching student's level, program, and current term
    courses = Course.objects.filter(
        level=instance.level,
        program=instance.program,
        term=current_term.term,
        is_core_subject=True,
        school=school
    )
    
    # Create TakenCourse records if they don't exist
    enrolled_count = 0
    for course in courses:
        taken_course, created_now = TakenCourse.objects.get_or_create(
            student=instance,
            course=course,
            school=school
        )
        if created_now:
            enrolled_count += 1
    
    # Sync attendance records (ensure summary exists)
    sync_attendance_records(instance, school)
    
    # Log the enrollment activity
    if enrolled_count > 0:
        ActivityLog.objects.create(
            message=_(f"Student '{instance.student.get_full_name}' auto-enrolled in {enrolled_count} course(s) for {instance.level}")
        )


@receiver(post_save, sender=Course)
def enroll_existing_students_in_new_course(sender, instance, created, **kwargs):
    """
    When a new core course is created, automatically enroll all students
    in the matching level/program.
    """
    # Skip if this is being loaded from a fixture or not a new course
    if kwargs.get('raw', False) or not created:
        return
    
    # Only auto-enroll for core subjects
    if not instance.is_core_subject:
        return
    
    # Get current term
    current_term = Term.objects.filter(is_current_term=True, school=instance.school).first()
    if not current_term or instance.term != current_term.term:
        # Only auto-enroll for current term courses
        return
    
    # Find all students matching this course's level and program
    students = Student.objects.filter(
        level=instance.level,
        program=instance.program,
        student__school=instance.school
    )
    
    # Enroll students in this course
    enrolled_count = 0
    for student in students:
        taken_course, created_now = TakenCourse.objects.get_or_create(
            student=student,
            course=instance,
            school=instance.school
        )
        if created_now:
            enrolled_count += 1
    
    # Log the enrollment activity
    if enrolled_count > 0:
        ActivityLog.objects.create(
            message=_(f"Course '{instance}' created - {enrolled_count} student(s) auto-enrolled")
        )


# Track previous values to detect changes
@receiver(pre_save, sender=Student)
def track_student_changes(sender, instance, **kwargs):
    """
    Track if student's level or program is changing to handle re-enrollment.
    """
    if instance.pk:
        try:
            old_instance = Student.objects.get(pk=instance.pk)
            instance._level_changed = old_instance.level != instance.level
            instance._program_changed = old_instance.program != instance.program
        except Student.DoesNotExist:
            instance._level_changed = False
            instance._program_changed = False
    else:
        instance._level_changed = False
        instance._program_changed = False


@receiver(post_save, sender=Student)
def handle_student_level_program_change(sender, instance, created, **kwargs):
    """
    When a student's level or program changes, re-enroll them in appropriate courses.
    Keep historical TakenCourse records but add new ones for the new level/program.
    """
    # Skip if this is being loaded from a fixture or is a new student (already handled)
    if kwargs.get('raw', False) or created:
        return
    
    # Check if level or program changed
    level_changed = getattr(instance, '_level_changed', False)
    program_changed = getattr(instance, '_program_changed', False)
    
    if not (level_changed or program_changed):
        return
    
    # Re-run the auto-enrollment logic
    auto_enroll_student_in_courses(sender, instance, False, **kwargs)
    
    # Log the change
    if level_changed and program_changed:
        ActivityLog.objects.create(
            message=_(f"Student '{instance.student.get_full_name}' changed level and program - courses updated")
        )
    elif level_changed:
        ActivityLog.objects.create(
            message=_(f"Student '{instance.student.get_full_name}' changed level to {instance.level} - courses updated")
        )
    elif program_changed:
        ActivityLog.objects.create(
            message=_(f"Student '{instance.student.get_full_name}' changed program to {instance.program} - courses updated")
        )
@receiver(post_save, sender=User)
def auto_allocate_courses_to_teacher(sender, instance, created, **kwargs):
    """
    When a teacher is assigned a level (class), automatically allocate
    all core courses for that level to them.
    """
    if kwargs.get('raw', False) or not instance.assigned_level:
        return
    
    if not (instance.is_teacher or instance.is_lecturer or instance.is_class_teacher):
        return
        
    school = instance.school
    if not school:
        return
        
    current_term = Term.objects.filter(is_current_term=True, school=school).first()
    if not current_term:
        return
        
    # Get all core courses for this level
    courses = Course.objects.filter(
        level=instance.assigned_level,
        term=current_term.term,
        is_core_subject=True,
        school=school
    )
    
    if not courses.exists():
        return
        
    # Get or create allocation for this teacher
    allocation, created_alloc = CourseAllocation.objects.get_or_create(
        teacher=instance
    )
    
    # Add courses to allocation
    allocation.courses.add(*courses)
    
    # Log activity
    ActivityLog.objects.create(
        message=_(f"Teacher '{instance.get_full_name}' auto-allocated courses for {instance.assigned_level}")
    )
