from django.contrib import admin
from django.utils.html import format_html
from .models import CourseFile, CourseVideo


@admin.register(CourseFile)
class CourseFileAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'file_type', 'uploaded_by', 'school', 'downloads', 'upload_time']
    list_filter = ['school', 'upload_time', 'uploaded_by']
    search_fields = ['title', 'description', 'course__title']
    readonly_fields = ['downloads', 'upload_time', 'updated_date']
    autocomplete_fields = ['course', 'uploaded_by', 'school']
    
    fieldsets = (
        ('File Information', {
            'fields': ('title', 'course', 'file', 'description')
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'school', 'downloads')
        }),
        ('Timestamps', {
            'fields': ('upload_time', 'updated_date'),
            'classes': ('collapse',)
        }),
    )
    
    def file_type(self, obj):
        return obj.get_extension_short().upper()
    file_type.short_description = 'Type'


@admin.register(CourseVideo)
class CourseVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'thumbnail_preview', 'uploaded_by', 'views', 'duration', 'timestamp']
    list_filter = ['school', 'timestamp', 'uploaded_by']
    search_fields = ['title', 'description', 'course__title']
    readonly_fields = ['slug', 'views', 'timestamp', 'updated_at', 'thumbnail_preview']
    autocomplete_fields = ['course', 'uploaded_by', 'school']
    
    fieldsets = (
        ('Video Information', {
            'fields': ('title', 'slug', 'course', 'video', 'thumbnail', 'thumbnail_preview', 'description')
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'school', 'duration', 'views')
        }),
        ('Timestamps', {
            'fields': ('timestamp', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html('<img src="{}" width="100" height="60" style="object-fit: cover;" />', obj.thumbnail.url)
        return '-'
    thumbnail_preview.short_description = 'Preview'
