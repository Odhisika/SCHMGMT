from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import Student
from course.models import Course
from result.models import TakenCourse


class Command(BaseCommand):
    help = "Enroll all students in courses matching their assigned level"

    def handle(self, *args, **options):
        self.stdout.write("Starting student enrollment process...")
        
        students = Student.objects.filter(level__isnull=False).select_related('student__school')
        total_students = students.count()
        
        self.stdout.write(f"Found {total_students} students with assigned levels")
        
        enrolled_total = 0
        skipped_total = 0
        
        with transaction.atomic():
            for idx, student in enumerate(students, 1):
                school = student.student.school if hasattr(student, 'student') else None
                
                # Get courses for this student's level and school
                courses = Course.objects.filter(
                    level=student.level,
                    school=school
                )
                
                student_enrolled = 0
                student_skipped = 0
                
                for course in courses:
                    _, created = TakenCourse.objects.get_or_create(
                        student=student,
                        course=course,
                        defaults={'school': school}
                    )
                    
                    if created:
                        student_enrolled += 1
                    else:
                        student_skipped += 1
                
                enrolled_total += student_enrolled
                skipped_total += student_skipped
                
                self.stdout.write(
                    f"  [{idx}/{total_students}] {student.student.get_full_name} ({student.level}): "
                    f"Enrolled in {student_enrolled} new courses, {student_skipped} already enrolled"
                )
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Enrollment complete!"
        ))
        self.stdout.write(f"  Total new enrollments: {enrolled_total}")
        self.stdout.write(f"  Already enrolled: {skipped_total}")
