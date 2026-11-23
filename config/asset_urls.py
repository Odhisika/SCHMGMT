"""URL helpers for serving user-uploaded media outside of DEBUG mode.

Django's ``static()`` helper is deliberately a no-op when DEBUG is False, so
simply removing DEBUG from the URLconfs would make every ``/media/`` URL 404
on production. Static assets (CSS/JS) are handled by WhiteNoise; these
patterns are a lightweight fallback for media when the web server is not
configured to serve MEDIA_ROOT directly.
"""

import re
from urllib.parse import urlsplit

from django.conf import settings
from django.urls import re_path
from django.views.static import serve


def media_urlpatterns():
    """Return a pattern for MEDIA_URL that works with DEBUG=False."""
    media_url = settings.MEDIA_URL
    if not media_url or urlsplit(media_url).netloc:
        # Remote media (e.g. S3/CDN) is served by its own storage backend.
        return []

    prefix = media_url.lstrip("/")
    if not prefix.endswith("/"):
        prefix += "/"

    return [
        re_path(
            r"^%s(?P<path>.*)$" % re.escape(prefix),
            serve,
            {"document_root": settings.MEDIA_ROOT},
            name="media-fallback",
        ),
    ]
