"""Helpers for creating and reading in-app notifications.

Every query in this module is scoped to a school and to the audiences the
user belongs to. This keeps notifications tenant-safe and prevents users
from seeing notifications meant for a different role (for example, a
teacher must never see an administrator-only notification).
"""

from django.db.models import Exists, OuterRef, Q

from .models import Notification


def audiences_for(user):
    """Return every audience a user belongs to."""
    if not user or not user.is_authenticated:
        return []

    audiences = [Notification.AUDIENCE_ALL]

    if user.is_superuser or user.is_school_admin:
        audiences.append(Notification.AUDIENCE_ADMIN)
    if user.is_teacher or user.is_lecturer or user.is_class_teacher:
        audiences.append(Notification.AUDIENCE_TEACHER)
    if user.is_student:
        audiences.append(Notification.AUDIENCE_STUDENT)
    if user.is_parent:
        audiences.append(Notification.AUDIENCE_PARENT)

    return audiences


def visible_notifications(user, school):
    """Notifications the given user is allowed to see in the given school."""
    if not user or not user.is_authenticated:
        return Notification.objects.none()

    # A role flag is not a tenant membership. In particular, an administrator
    # must not see another school's ADMIN audience just because their account
    # has the administrator role. Superusers may switch tenant context.
    if not user.is_superuser and (
        school is None or getattr(user, "school_id", None) != school.pk
    ):
        return Notification.objects.none()

    queryset = Notification.objects.select_related("actor")
    if school is None:
        queryset = queryset.filter(school__isnull=True)
    else:
        queryset = queryset.filter(school=school)

    audience_query = Q(recipient__isnull=True, audience__in=audiences_for(user))
    if not (user.is_superuser or user.is_school_admin):
        audience_query &= Q(division="") | Q(division=user.division or "")

    return queryset.filter(Q(recipient=user) | audience_query).distinct()


def annotate_read_state(queryset, user):
    """Attach an ``is_read`` flag for the given user to each notification."""
    through = Notification.read_by.through
    read_records = through.objects.filter(
        notification_id=OuterRef("pk"),
        user_id=user.pk,
    )
    return queryset.annotate(is_read=Exists(read_records))


def unread_count(user, school):
    """Number of unread notifications visible to the user."""
    return visible_notifications(user, school).exclude(read_by=user).count()


def recent_notifications(user, school, limit=8):
    """Latest unread notifications for the navbar attention dropdown."""
    return list(
        annotate_read_state(
            visible_notifications(user, school).exclude(read_by=user), user
        )[:limit]
    )


def mark_all_read(user, school):
    """Mark every visible notification as read for the given user."""
    through = Notification.read_by.through
    already_read = through.objects.filter(user_id=user.pk).values_list(
        "notification_id", flat=True
    )
    notification_ids = list(
        visible_notifications(user, school)
        .exclude(pk__in=already_read)
        .values_list("pk", flat=True)
    )
    if notification_ids:
        through.objects.bulk_create(
            [
                through(notification_id=notification_id, user_id=user.pk)
                for notification_id in notification_ids
            ],
            ignore_conflicts=True,
        )
    return len(notification_ids)


def notify(
    school,
    title,
    message="",
    link="",
    notification_type=Notification.TYPE_INFO,
    audience=Notification.AUDIENCE_ALL,
    recipient=None,
    actor=None,
    division="",
):
    """Create a notification.

    Passing ``recipient`` creates a personal notification. Otherwise an
    audience notification is created and shared by everyone in that role
    within the school.
    """
    if recipient is not None:
        if actor is not None and actor.pk == recipient.pk:
            return None
        audience = Notification.AUDIENCE_USER
        school = school or recipient.school

        # Keep personal notifications inside the recipient's tenant as well.
        if recipient.school_id is None or recipient.school_id != getattr(school, "pk", None):
            return None

    if school is None:
        return None

    return Notification.objects.create(
        school=school,
        recipient=recipient,
        audience=audience,
        title=title,
        message=message,
        link=link,
        notification_type=notification_type,
        actor=actor,
        division=division or "",
    )


def notify_admins(school, title, message="", link="", notification_type=Notification.TYPE_INFO, actor=None, division=""):
    return notify(
        school,
        title,
        message=message,
        link=link,
        notification_type=notification_type,
        audience=Notification.AUDIENCE_ADMIN,
        actor=actor,
        division=division,
    )


def notify_teachers(school, title, message="", link="", notification_type=Notification.TYPE_INFO, actor=None, division=""):
    return notify(
        school,
        title,
        message=message,
        link=link,
        notification_type=notification_type,
        audience=Notification.AUDIENCE_TEACHER,
        actor=actor,
        division=division,
    )


def notify_students(school, title, message="", link="", notification_type=Notification.TYPE_INFO, actor=None, division=""):
    return notify(
        school,
        title,
        message=message,
        link=link,
        notification_type=notification_type,
        audience=Notification.AUDIENCE_STUDENT,
        actor=actor,
        division=division,
    )


def notify_parents(school, title, message="", link="", notification_type=Notification.TYPE_INFO, actor=None, division=""):
    return notify(
        school,
        title,
        message=message,
        link=link,
        notification_type=notification_type,
        audience=Notification.AUDIENCE_PARENT,
        actor=actor,
        division=division,
    )
