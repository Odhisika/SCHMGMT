from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from .models import Notification, Semester, NewsAndEvents


class NewsAndEventsAdmin(TranslationAdmin):
    pass


class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "audience",
        "recipient",
        "school",
        "notification_type",
        "created_at",
    )
    list_filter = ("audience", "notification_type", "school")
    search_fields = ("title", "message", "recipient__username")
    autocomplete_fields = ("recipient", "actor")


admin.site.register(Semester)
admin.site.register(NewsAndEvents, NewsAndEventsAdmin)
admin.site.register(Notification, NotificationAdmin)
