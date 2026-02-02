from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views import defaults as default_views
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog

# Public / School URLs
# This file is loaded for ALL school domains (e.g. greenwood.localhost)
# It strictly EXCLUDES the Super Admin Portal for security.

urlpatterns = [
    # No /superadmin/ here!
    
    # We keep /admin/ for School Staff (if you want them to use Django Admin, 
    # though usually we restrict this. Leaving it for now but secured by permissions).
    path("backend/", admin.site.urls), # Renamed from 'admin' to hide it slightly
    
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("", include("core.urls")),
    # path("jet/", include("jet.urls", "jet")),  # Disable JET for schools to simplify
    # path("jet/dashboard/", include("jet.dashboard.urls", "jet-dashboard")),
    
    path("accounts/", include("accounts.urls")),
    path("programs/", include("course.urls")),
    path("result/", include("result.urls")),
    path("search/", include("search.urls")),
    path("quiz/", include("quiz.urls")),
    path("payments/", include("payments.urls")),
    path("school/", include("school.urls")),
    path("timetable/", include("timetable.urls")),
)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += [
        path("400/", default_views.bad_request, kwargs={"exception": Exception("Bad Request!")}),
        path("403/", default_views.permission_denied, kwargs={"exception": Exception("Permission Denied")}),
        path("404/", default_views.page_not_found, kwargs={"exception": Exception("Page not Found")}),
        path("500/", default_views.server_error),
    ]
