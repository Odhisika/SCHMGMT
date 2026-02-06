from django.contrib import admin
from .models import User, Student, Parent


class UserAdmin(admin.ModelAdmin):
    list_display = [
        "get_full_name",
        "username",
        "email",
        "is_active",
        "is_parent",
        "is_staff",
        "assigned_level",
    ]
    search_fields = [
        "username",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "is_lecturer",
        "is_parent",
        "is_staff",
    ]

    class Meta:
        managed = True
        verbose_name = "User"
        verbose_name_plural = "Users"


admin.site.register(User, UserAdmin)
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['student', 'level', 'program', 'school']
    search_fields = ['student__username', 'student__first_name', 'student__last_name']
    list_filter = ['level', 'program', 'student__school']
    actions = ['sync_selected_students']

    def school(self, obj):
        return obj.student.school
    school.short_description = 'School'

    def sync_selected_students(self, request, queryset):
        from result.models import TakenCourse
        from core.models import Term
        from fees.models import FeeStructure, StudentFeeAssignment
        from attendance.utils import sync_attendance_records
        from django.db.models import Q
        from django.contrib import messages

        success_count = 0
        for student in queryset:
            school = student.student.school
            if not school: continue
            
            current_term = Term.objects.filter(is_current_term=True, school=school).first()
            if not current_term: continue

            # Sync Courses
            courses = __import__('course.models', fromlist=['Course']).Course.objects.filter(
                level=student.level,
                program=student.program,
                term=current_term.term,
                is_core_subject=True,
                school=school
            )
            for course in courses:
                TakenCourse.objects.get_or_create(student=student, course=course, school=school)

            # Sync Fees
            fee_structures = FeeStructure.objects.filter(
                school=school, is_active=True, auto_assign=True
            ).filter(
                Q(level=student.level) | Q(level='')
            ).filter(
                Q(term=current_term.term) | Q(term='')
            )
            for fs in fee_structures:
                StudentFeeAssignment.objects.get_or_create(
                    student=student, fee_structure=fs, term=current_term,
                    defaults={'amount': fs.amount}
                )

            # Sync Attendance Summary
            sync_attendance_records(student, school)
            success_count += 1
        
        self.message_user(request, f"Successfully synchronized {success_count} students.", messages.SUCCESS)
    sync_selected_students.short_description = "Sync Enrollments, Fees & Attendance"


admin.site.register(Parent)
