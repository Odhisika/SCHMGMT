from django.contrib import admin
from .models import Period, TimetableEntry


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ['name', 'period_type', 'start_time', 'end_time', 'order', 'school']
    list_filter = ['school', 'period_type']
    search_fields = ['name']
    ordering = ['school', 'order']


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ['level', 'day_of_week', 'period', 'subject', 'teacher', 'term', 'school']
    list_filter = ['school', 'term', 'level', 'day_of_week', 'period__period_type']
    search_fields = ['subject__title', 'teacher__first_name', 'teacher__last_name']
    autocomplete_fields = ['subject', 'teacher']
    ordering = ['school', 'term', 'level', 'day_of_week', 'period__order']
