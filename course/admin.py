from django.contrib import admin
from django.contrib.auth.models import Group

from .models import Program, Course, CourseAllocation, Upload, LessonNote, SubjectTemplate
from modeltranslation.admin import TranslationAdmin

class ProgramAdmin(TranslationAdmin):
    list_display = ['title', 'division', 'is_academic_block', 'school']
    list_filter = ['division', 'is_academic_block', 'school']
    search_fields = ['title', 'summary']
    
class CourseAdmin(TranslationAdmin):
    list_display = ['title', 'code', 'level', 'program', 'term', 'is_core_subject']
    list_filter = ['level', 'term', 'is_core_subject', 'is_elective', 'school']
    search_fields = ['title', 'code', 'summary']
    
class UploadAdmin(TranslationAdmin):
    pass

class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'course', 'term', 'week_number', 'status', 'created_at']
    list_filter = ['status', 'term', 'course']
    search_fields = ['title', 'topic', 'teacher__first_name', 'teacher__last_name', 'course__title']
    readonly_fields = ['teacher', 'submitted_at', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at']

class SubjectTemplateAdmin(admin.ModelAdmin):
    list_display = ['title', 'code_prefix', 'level', 'division', 'is_core_subject', 'is_elective', 'school']
    list_filter = ['division', 'level', 'is_core_subject', 'is_elective', 'school']
    search_fields = ['title', 'code_prefix', 'description']
    fields = ['title', 'code_prefix', 'level', 'division', 'is_core_subject', 'is_elective', 'description', 'school']

admin.site.register(Program, ProgramAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(CourseAllocation)
admin.site.register(Upload, UploadAdmin)
admin.site.register(LessonNote, LessonNoteAdmin)
admin.site.register(SubjectTemplate, SubjectTemplateAdmin)
