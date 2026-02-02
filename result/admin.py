from django.contrib import admin
from django.contrib.auth.models import Group

from .models import TakenCourse, Result, BECEMockExam, BECEMockResult


class ScoreAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "course",
        "class_score",
        "exam_score",
        "total",
        "grade",
        "class_position",
        "comment",
    ]
    list_filter = ["student__level", "course__term"]
    search_fields = ["student__student__first_name", "student__student__last_name", "course__title"]


@admin.register(BECEMockExam)
class BECEMockExamAdmin(admin.ModelAdmin):
    list_display = ['name', 'year', 'date_started', 'is_active']
    list_filter = ['year', 'is_active']


@admin.register(BECEMockResult)
class BECEMockResultAdmin(admin.ModelAdmin):
    list_display = ['student', 'mock_exam', 'course', 'score', 'grade']
    list_filter = ['mock_exam', 'course', 'grade']
    search_fields = ['student__student__first_name', 'student__student__last_name']


admin.site.register(TakenCourse, ScoreAdmin)
admin.site.register(Result)

