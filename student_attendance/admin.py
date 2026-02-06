from django.contrib import admin
from .models import AttendanceSession, AttendanceRecord


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ['date', 'level', 'school', 'marked_by', 'total_students', 'present_count', 'absent_count']
    list_filter = ['date', 'level', 'school']
    search_fields = ['level', 'notes']
    readonly_fields = ['marked_at']


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['student', 'session', 'status', 'notes']
    list_filter = ['status', 'session__date', 'session__level']
    search_fields = ['student__student__first_name', 'student__student__last_name', 'notes']
