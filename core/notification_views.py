from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .notifications import (
    annotate_read_state,
    mark_all_read,
    recent_notifications,
    unread_count,
    visible_notifications,
)


def _notification_school(request):
    """Resolve the tenant whose notifications are being displayed."""
    return getattr(request, "school", None) or getattr(request.user, "school", None)


def _widget_context(request):
    school = _notification_school(request)
    return {
        "unread_notifications_count": unread_count(request.user, school),
        "recent_notifications": recent_notifications(request.user, school, limit=8),
    }


@login_required
def notification_list(request):
    """Full notification center page."""
    school = _notification_school(request)
    queryset = annotate_read_state(
        visible_notifications(request.user, school),
        request.user,
    )

    current_filter = request.GET.get("filter", "unread")
    if current_filter == "unread":
        queryset = queryset.filter(is_read=False)
    elif current_filter == "all":
        current_filter = "all"
    else:
        current_filter = "all"

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "notifications/list.html",
        {
            "page_obj": page_obj,
            "notifications": page_obj.object_list,
            "unread_notifications_count": unread_count(request.user, school),
            "current_filter": current_filter,
            "title": "Notifications",
        },
    )


@login_required
def notification_widget(request):
    """HTMX endpoint that refreshes the navbar notification dropdown."""
    return render(request, "notifications/widget.html", _widget_context(request))


@login_required
def notification_open(request, pk):
    """Mark one notification as read and follow its link, if any."""
    school = _notification_school(request)
    notification = get_object_or_404(
        visible_notifications(request.user, school),
        pk=pk,
    )

    notification.read_by.add(request.user)

    link = (notification.link or "").strip()
    if link and url_has_allowed_host_and_scheme(
        link,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(link)

    return redirect("notification_list")


@login_required
@require_POST
def notification_mark_all_read(request):
    """Mark all visible notifications as read for the current user."""
    school = _notification_school(request)
    count = mark_all_read(request.user, school)

    if request.headers.get("HX-Request") == "true":
        return render(request, "notifications/widget.html", _widget_context(request))

    if count:
        messages.success(request, "All notifications marked as read.")
    else:
        messages.info(request, "You have no unread notifications.")
    return redirect("notification_list")
