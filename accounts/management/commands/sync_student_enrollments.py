"""
Management command to sync existing students with their class courses.
Enrolls all students in courses for their assigned level.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import Student  
from course.models import Course
from result.models import TakenCourse


class Command(BaseCommand):
    help = 'Auto-enroll all existing students in courses for their assigned levels'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--level',
            type=str,
            help='Only sync students at this level (e.g., "Primary 1")',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        level_filter = options.get('level')
        
        # Get students
        students = Student.objects.all().select_related('student')
        if level_filter:
            students = students.filter(level=level_filter)
        
        total_students = students.count()
        students_with_level = students.exclude(level__isnull=True).exclude(level='')
        
        self.stdout.write(self.style.SUCCESS(
            f'Found {students_with_level.count()} students with assigned levels out of {total_students} total students'
        ))
        
        total_enrolled = 0
        students_processed = 0
        
        for student in students_with_level:
            school = student.student.school if hasattr(student, 'student') else None
            
            # Get all courses for this student's level and school
            courses = Course.objects.filter(
                level=student.level,
                school=school
            )
            
            if courses.count() == 0:
                self.stdout.write(self.style.WARNING(
                    f'No courses found for level "{student.level}" at school {school}'
                ))
                continue
            
            enrolled_count = 0
            for course in courses:
                if dry_run:
                    # Check if enrollment exists
                    exists = TakenCourse.objects.filter(
                        student=student,
                        course=course
                    ).exists()
                    if not exists:
                        enrolled_count += 1
                        self.stdout.write(
                            f'  [DRY RUN] Would enroll {student.student.get_full_name} in {course.title}'
                        )
                else:
                    # Create enrollment
                    with transaction.atomic():
                        taken_course, created = TakenCourse.objects.get_or_create(
                            student=student,
                            course=course,
                            defaults={'school': school}
                        )
                        if created:
                            enrolled_count += 1
            
            if enrolled_count > 0:
                total_enrolled += enrolled_count
                students_processed += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Enrolled {student.student.get_full_name} ({student.level}) in {enrolled_count} courses'
                    )
                )
        
        # Summary
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\n[DRY RUN] Would have enrolled {students_processed} students in {total_enrolled} total course enrollments'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Successfully enrolled {students_processed} students in {total_enrolled} total course enrollments'
            ))
