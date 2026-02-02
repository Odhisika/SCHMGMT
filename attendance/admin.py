from django.contrib import admin
from .models import Attendance, AttendanceSummary


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'date', 'status', 'subject', 'recorded_by']
    list_filter = ['status', 'date', 'student__level']
    search_fields = ['student__student__first_name', 'student__student__last_name']
    date_hierarchy = 'date'
    autocomplete_fields = ['student', 'subject', 'recorded_by']


@admin.register(AttendanceSummary)
class AttendanceSummaryAdmin(admin.ModelAdmin):
    list_display = ['student', 'term', 'days_present', 'days_absent', 'attendance_percentage']
    list_filter = ['term', 'student__level']
    search_fields = ['student__student__first_name', 'student__student__last_name']
    readonly_fields = ['attendance_percentage']
