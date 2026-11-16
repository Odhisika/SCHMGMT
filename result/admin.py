from django.contrib import admin
from django.contrib.auth.models import Group

from .models import (
    BECEMockExam,
    BECEMockResult,
    PromotionDecision,
    PromotionRequest,
    Result,
    TakenCourse,
)


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


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "term",
        "session",
        "level",
        "term_average",
        "promotion_status",
        "promoted",
        "school",
    ]
    list_filter = ["term", "session", "level", "promotion_status", "school"]
    search_fields = [
        "student__student__first_name",
        "student__student__last_name",
        "student__student__username",
    ]


@admin.register(PromotionDecision)
class PromotionDecisionAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "session",
        "level",
        "terms_used",
        "average",
        "status",
        "decision",
        "is_final_class",
        "decided_at",
    ]
    list_filter = ["session", "level", "status", "decision", "is_final_class", "school"]
    search_fields = [
        "student__student__first_name",
        "student__student__last_name",
        "student__student__username",
    ]
    readonly_fields = ["decided_at"]


@admin.register(PromotionRequest)
class PromotionRequestAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "result",
        "request_type",
        "status",
        "requested_by",
        "reviewed_by",
        "created_at",
    ]
    list_filter = ["status", "request_type", "school"]
    search_fields = [
        "student__student__first_name",
        "student__student__last_name",
        "student__student__username",
    ]


admin.site.register(TakenCourse, ScoreAdmin)

