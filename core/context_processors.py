from .notifications import recent_notifications, unread_count


def notification_center(request):
    """Expose the navbar notification badge and dropdown to templates."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "unread_notifications_count": 0,
            "recent_notifications": [],
        }

    school = getattr(request, "school", None) or getattr(user, "school", None)
    return {
        "unread_notifications_count": unread_count(user, school),
        "recent_notifications": recent_notifications(user, school, limit=8),
    }
