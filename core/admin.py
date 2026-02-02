from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from .models import Semester, NewsAndEvents


class NewsAndEventsAdmin(TranslationAdmin):
    pass


admin.site.register(Semester)
admin.site.register(NewsAndEvents, NewsAndEventsAdmin)
