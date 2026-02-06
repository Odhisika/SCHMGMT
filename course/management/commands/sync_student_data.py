from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from accounts.models import Student
from course.models import Course
from result.models import TakenCourse
from core.models import Term, ActivityLog
from fees.models import FeeStructure, StudentFeeAssignment
from attendance.utils import sync_attendance_records

class Command(BaseCommand):
    help = 'Synchronize student enrollments, fees, and attendance for all students'

    def add_arguments(self, parser):
        parser.add_argument('--school', type=str, help='Filter by school slug')
        parser.add_argument('--level', type=str, help='Filter by level')

    def handle(self, *args, **options):
        school_slug = options.get('school')
        level_filter = options.get('level')
        
        students = Student.objects.all()
        if school_slug:
            students = students.filter(student__school__slug=school_slug)
        if level_filter:
            students = students.filter(level=level_filter)
            
        self.stdout.write(self.style.SUCCESS(f'Starting sync for {students.count()} students...'))
        
        total_enrolled = 0
        total_fees = 0
        
        for student in students:
            school = student.student.school
            if not school:
                continue
                
            current_term = Term.objects.filter(is_current_term=True, school=school).first()
            if not current_term:
                continue
                
            with transaction.atomic():
                # 1. Sync Courses (TakenCourse)
                courses = Course.objects.filter(
                    level=student.level,
                    program=student.program,
                    term=current_term.term,
                    is_core_subject=True,
                    school=school
                )
                
                for course in courses:
                    _, created = TakenCourse.objects.get_or_create(
                        student=student,
                        course=course,
                        school=school
                    )
                    if created:
                        total_enrolled += 1
                        
                # 2. Sync Fees
                fee_structures = FeeStructure.objects.filter(
                    school=school,
                    is_active=True,
                    auto_assign=True
                ).filter(
                    # Match level (or blank for all levels)
                    models_Q := __import__('django.db.models', fromlist=['Q']).Q,
                    models_Q(level=student.level) | models_Q(level='')
                ).filter(
                    models_Q(term=current_term.term) | models_Q(term='')
                )
                
                for fs in fee_structures:
                    _, created = StudentFeeAssignment.objects.get_or_create(
                        student=student,
                        fee_structure=fs,
                        term=current_term,
                        defaults={'amount': fs.amount}
                    )
                    if created:
                        total_fees += 1
                        
                # 3. Sync Attendance Summary
                sync_attendance_records(student, school)
                
        self.stdout.write(self.style.SUCCESS(
            f'Sync completed: {total_enrolled} course enrollments created, {total_fees} fee assignments created.'
        ))
        
        ActivityLog.objects.create(
            message=_(f"Manual sync completed: {total_enrolled} enrollments, {total_fees} fees.")
        )
