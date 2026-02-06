from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns

from django.views.i18n import JavaScriptCatalog

# Super Admin / Master Console URLs
# This file is ONLY loaded when accessing via the Admin Domain (e.g. admin.localhost)

admin.site.site_header = "SkyLearn Master Console"

urlpatterns = [
    # JavaScript Catalog for i18n
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),

    # Direct access to Super Admin Portal at root
    path("", include("superadmin.urls")),
    # Also support /superadmin/ for muscle memory
    path("superadmin/", include("superadmin.urls")),
    
    # We still need authentication
    path("accounts/", include("accounts.urls")),
    path("attendance/", include("attendance.urls")),
    path("fees/", include("fees.urls")),
    
    # Django Admin for low-level debugging
    path("django-admin/", admin.site.urls),
    
    # i18n support
    path("i18n/", include("django.conf.urls.i18n")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
