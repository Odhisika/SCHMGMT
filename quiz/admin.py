from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TranslationAdmin
from modeltranslation.forms import TranslationModelForm

from .models import (
    Quiz,
    Progress,
    Question,
    MCQuestion,
    Choice,
    EssayQuestion,
    TrueFalseQuestion,
    FillInTheBlankQuestion,
    Assignment,
    AssignmentSubmission,
    Sitting,
)


class ChoiceInline(admin.TabularInline):
    model = Choice


class QuizAdminForm(TranslationModelForm):
    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.all().select_subclasses(),
        required=False,
        label=_("Questions"),
        widget=FilteredSelectMultiple(verbose_name=_("Questions"), is_stacked=False),
    )

    class Meta:
        model = Quiz
        fields = ["title_en"]

    def __init__(self, *args, **kwargs):
        super(QuizAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["questions"].initial = (
                self.instance.question_set.all().select_subclasses()
            )

    def save(self, commit=True):
        quiz = super(QuizAdminForm, self).save(commit=False)
        quiz.save()
        quiz.question_set.set(self.cleaned_data["questions"])
        self.save_m2m()
        return quiz


class QuizAdmin(TranslationAdmin):
    list_display = ('title', 'course', 'category', 'available_from', 'available_until', 'time_limit_minutes', 'draft')
    list_filter = ('category', 'draft', 'exam_paper', 'single_attempt')
    search_fields = ('title', 'description')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'course', 'description', 'category')
        }),
        ('Quiz Settings', {
            'fields': ('random_order', 'answers_at_end', 'exam_paper', 'single_attempt', 'pass_mark', 'draft')
        }),
        ('Scheduling & Availability', {
            'fields': ('available_from', 'available_until'),
            'description': 'Set when the quiz is available to students'
        }),
        ('Time Limits', {
            'fields': ('time_limit_minutes',),
            'description': 'Leave blank for unlimited time'
        }),
        ('Answer Display', {
            'fields': ('allow_review_after_submission', 'show_correct_answers_after'),
            'description': 'Control when students can see answers'
        }),
    )
    # form = QuizAdminForm
    # fields = (
    #     "title",
    #     "description",
    # )
    # list_display = ("title",)
    # # list_filter = ('category',)
    # search_fields = (
    #     "description",
    #     "category",
    # )


class MCQuestionAdmin(TranslationAdmin):
    list_display = ("content",)
    # list_filter = ('category',)
    fieldsets = [
        ("figure" "quiz" "choice_order", {"fields": ("content", "explanation")})
    ]

    search_fields = ("content", "explanation")
    filter_horizontal = ("quiz",)

    inlines = [ChoiceInline]


class ProgressAdmin(admin.ModelAdmin):
    search_fields = (
        "user",
        "score",
    )


class EssayQuestionAdmin(admin.ModelAdmin):
    list_display = ("content",)
    # list_filter = ('category',)
    fields = (
        "content",
        "quiz",
        "explanation",
    )
    search_fields = ("content", "explanation")
    filter_horizontal = ("quiz",)


class TrueFalseQuestionAdmin(admin.ModelAdmin):
    list_display = ("content", "correct_answer")
    fields = (
        "content",
        "quiz",
        "correct_answer",
        "explanation",
        "figure",
    )
    search_fields = ("content", "explanation")
    filter_horizontal = ("quiz",)


class FillInTheBlankQuestionAdmin(admin.ModelAdmin):
    list_display = ("content", "correct_answer", "case_sensitive")
    fields = (
        "content",
        "quiz",
        "correct_answer",
        "case_sensitive",
        "explanation",
        "figure",
    )
    search_fields = ("content", "explanation")
    filter_horizontal = ("quiz",)


class AssignmentSubmissionInline(admin.TabularInline):
    model = AssignmentSubmission
    extra = 0
    readonly_fields = ("student", "submitted_file", "submission_date", "is_late")
    fields = ("student", "submission_date", "grade", "feedback", "is_late")


class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "quiz", "due_date", "max_score", "is_overdue")
    list_filter = ("due_date", "quiz__course")
    search_fields = ("title", "description")
    fields = (
        "quiz",
        "title",
        "description",
        "file",
        "due_date",
        "max_score",
    )
    inlines = [AssignmentSubmissionInline]


class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "assignment", "submission_date", "grade", "is_late", "is_graded")
    list_filter = ("submission_date", "assignment")
    search_fields = ("student__username", "student__first_name", "student__last_name", "assignment__title")
    readonly_fields = ("submission_date", "is_late")
    fields = (
        "assignment",
        "student",
        "submitted_file",
        "submission_text",
        "submission_date",
        "grade",
        "feedback",
        "graded_by",
        "graded_at",
        "is_late",
    )


admin.site.register(Quiz, QuizAdmin)
admin.site.register(MCQuestion, MCQuestionAdmin)
admin.site.register(Progress, ProgressAdmin)
admin.site.register(EssayQuestion, EssayQuestionAdmin)
admin.site.register(TrueFalseQuestion, TrueFalseQuestionAdmin)
admin.site.register(FillInTheBlankQuestion, FillInTheBlankQuestionAdmin)
admin.site.register(Assignment, AssignmentAdmin)
admin.site.register(AssignmentSubmission, AssignmentSubmissionAdmin)
admin.site.register(Sitting)
