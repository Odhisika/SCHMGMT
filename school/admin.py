from django.contrib import admin
from .models import School

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "email", "created_at")
    search_fields = ("name", "email")
    prepopulated_fields = {"slug": ("name",)}
