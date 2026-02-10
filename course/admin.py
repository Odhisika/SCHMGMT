from django.contrib import admin
from django.contrib.auth.models import Group

from .models import Program, Course, CourseAllocation, Upload, LessonNote
from modeltranslation.admin import TranslationAdmin

class ProgramAdmin(TranslationAdmin):
    pass
class CourseAdmin(TranslationAdmin):
    search_fields = ['title', 'code']
class UploadAdmin(TranslationAdmin):
    pass

class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'course', 'term', 'week_number', 'status', 'created_at']
    list_filter = ['status', 'term', 'course']
    search_fields = ['title', 'topic', 'teacher__first_name', 'teacher__last_name', 'course__title']
    readonly_fields = ['teacher', 'submitted_at', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at']

admin.site.register(Program, ProgramAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(CourseAllocation)
admin.site.register(Upload, UploadAdmin)
admin.site.register(LessonNote, LessonNoteAdmin)
