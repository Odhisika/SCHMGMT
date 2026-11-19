import random
import string
from datetime import timedelta
from django.utils.text import slugify
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.conf import settings


def get_week_date_range(term, week_number):
    """Return the Monday and Friday dates for a numbered term week.

    Week 1 is the Monday-Friday week containing the term's start date, week 2
    is the following Monday-Friday, and so on. This matches the way attendance
    is grouped into weeks (see ``attendance.views.get_weekly_attendance_data``).
    """
    if not term or not term.start_date or not week_number:
        return None, None
    first_monday = term.start_date - timedelta(days=term.start_date.weekday())
    monday = first_monday + timedelta(days=(int(week_number) - 1) * 7)
    return monday, monday + timedelta(days=4)


def get_week_dates(term, week):
    """Return the dates to display for a week (configured or derived).

    Older week rows were seeded without dates, so fall back to the term's
    Monday-Friday calendar week instead of showing nothing.
    """
    if not week:
        return None, None
    if week.start_date and week.end_date:
        return week.start_date, week.end_date
    return get_week_date_range(term, week.week_number)


def get_current_term_week(term, weeks):
    """Return the week that should be shown as the current week.

    An explicit date range containing today always wins. Otherwise the week
    number is derived from Monday-based calendar weeks counted from the term's
    start week. Once today is past the configured weeks the latest week stays
    selected, so the homepage never snaps back to week 1.
    """
    weeks = list(weeks)
    if not weeks:
        return None

    today = timezone.localdate()
    earliest_week = min(weeks, key=lambda week: week.week_number)

    for week in weeks:
        if (
            week.start_date
            and week.end_date
            and week.start_date <= today <= week.end_date
        ):
            return week

    if not term or not term.start_date:
        return earliest_week

    first_monday = term.start_date - timedelta(days=term.start_date.weekday())
    if today < first_monday:
        return earliest_week

    week_number = ((today - first_monday).days // 7) + 1
    # Pick the greatest configured week that has started; this also handles
    # gaps from deleted weeks and keeps the last week selected after term end.
    started = [week for week in weeks if week.week_number <= week_number]
    return max(started, key=lambda week: week.week_number) if started else earliest_week


def send_email(user, subject, msg):
    send_mail(
        subject,
        msg,
        settings.EMAIL_FROM_ADDRESS,
        [user.email],
        fail_silently=False,
    )


def send_html_email(subject, recipient_list, template, context):
    """A function responsible for sending HTML email"""
    # Render the HTML template
    html_message = render_to_string(template, context)

    # Generate plain text version of the email (optional)
    plain_message = strip_tags(html_message)

    # Send the email
    send_mail(
        subject,
        plain_message,
        settings.EMAIL_FROM_ADDRESS,
        recipient_list,
        html_message=html_message,
    )


def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, new_slug=None):
    """
    Assumes the instance has a model with a slug field and a title
    character (char) field.
    """
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(instance.title)

    klass = instance.__class__
    qs_exists = klass.objects.filter(slug=slug).exists()
    if qs_exists:
        new_slug = f"{slug}-{random_string_generator(size=4)}"
        return unique_slug_generator(instance, new_slug=new_slug)
    return slug
