from django.db import transaction
from django.utils.translation import gettext as _
from .models import Period, TimetableEntry
from course.models import Course, CourseAllocation
import random

def auto_generate_timetable(school, term):
    """
    Auto-generate timetable for all classes in the school.
    Returns (success: bool, message: str)
    """
    try:
        with transaction.atomic():
            # 1. Clear existing entries for this term to avoid duplicates
            # (Optional: In a real app, maybe ask user first. Here we assume overwrite or clean slate)
            # TimetableEntry.objects.filter(school=school, term=term).delete()
            
            # Instead of full delete, let's only generate for empty slots or skip conflicts
            # But the user request implies generating a fresh one usually.
            # Let's check if there are any entries first
            existing_count = TimetableEntry.objects.filter(school=school, term=term).count()
            if existing_count > 0:
                # For safety in this MVP, let's NOT auto-delete.
                # Only fill empty slots? Or maybe we should provide a "Clear" button separately.
                # User asked to "auto generate and edit".
                # Let's try to fill empty slots for now.
                pass

            # 2. Get lesson periods
            lesson_periods = Period.objects.filter(school=school, period_type='LESSON').order_by('order')
            if not lesson_periods.exists():
                return False, _("No lesson periods defined. Please create periods first.")

            days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY']
            
            # 3. Get all active classes (levels)
            # We iterate through levels defined in settings
            from django.conf import settings
            levels = [code for code, name in settings.LEVEL_CHOICES]
            
            for level in levels:
                # Get subjects for this level and term
                # Note: Course model has 'level' and 'term' CharFields
                # But 'term' in Course might be string "First", while 'term' obj is Term model
                # We need to match them. Term model has 'term' field choices same as settings.TERM_CHOICES
                
                subjects = Course.objects.filter(
                    school=school,
                    level=level,
                    # term=term.term # Assuming Course.term matches Term.term
                )
                
                # Filter subjects that match the current term
                # If Course.term is "First Term", ensure we match correctly
                subjects = subjects.filter(term=term.term)
                
                if not subjects.exists():
                    continue

                # Get teacher allocations for these subjects
                allocations = CourseAllocation.objects.filter(
                    courses__in=subjects
                ).select_related('teacher')
                
                # Map subject to teacher
                subject_teacher_map = {}
                for allocation in allocations:
                    for course in allocation.courses.all():
                        if course in subjects:
                            subject_teacher_map[course.id] = allocation.teacher

                # Strategy:
                # Create a list of slots (Day, Period)
                # Create a list of Lessons to teach (Subject * Frequency)
                # Shuffle lessons and fill slots
                
                slots = []
                for day in days:
                    for period in lesson_periods:
                        # Check if slot is already occupied
                        if not TimetableEntry.objects.filter(
                            school=school, term=term, level=level, day_of_week=day, period=period
                        ).exists():
                            slots.append((day, period))
                
                if not slots:
                    continue

                # Define frequency (how many times per week per subject)
                # Default: Core subjects more frequent
                lessons_pool = []
                for subject in subjects:
                    frequency = 3 # Default
                    if subject.is_core_subject: # Assuming property or check
                        frequency = 5
                    # Adjust frequency to not exceed available slots roughly
                    
                    # Add to pool
                    for i in range(frequency):
                        lessons_pool.append(subject)
                
                # Trim pool if larger than slots, or pad with Free Period (None)
                if len(lessons_pool) > len(slots):
                    lessons_pool = lessons_pool[:len(slots)]
                
                # Shuffle for randomness
                random.shuffle(lessons_pool)
                
                # Assign
                for i, (day, period) in enumerate(slots):
                    if i >= len(lessons_pool):
                        break
                        
                    subject = lessons_pool[i]
                    teacher = subject_teacher_map.get(subject.id)
                    
                    # Check teacher conflict
                    if teacher:
                        conflict = TimetableEntry.objects.filter(
                            school=school,
                            term=term,
                            day_of_week=day,
                            period=period,
                            teacher=teacher
                        ).exists()
                        if conflict:
                            # Simple retry/skip logic:
                            # Try to find another subject in the pool that doesn't conflict?
                            # For MVP simplicity: assign subject but leave teacher None (or note conflict)
                            # Or just skip assigning this slot to this subject?
                            # Let's skip assigning this specific subject to this slot to avoid error
                            continue
                    
                    TimetableEntry.objects.create(
                        school=school,
                        term=term,
                        level=level,
                        day_of_week=day,
                        period=period,
                        subject=subject,
                        teacher=teacher
                    )

            return True, _("Timetable generated successfully!")

    except Exception as e:
        return False, f"Error generating timetable: {str(e)}"
