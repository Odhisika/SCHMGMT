import logging
import threading
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.utils import send_html_email


logger = logging.getLogger(__name__)


def generate_password():
    return get_user_model().objects.make_random_password(length=16)


@transaction.atomic
def generate_student_id(school=None, division=None):
    """Allocate the next ID for a school's division, starting at 1."""
    UserModel = get_user_model()
    if school and division in ("Nursery", "Primary", "JHS"):
        from school.models import StudentIDSequence

        division_fields = {
            "Nursery": ("student_id_nursery_prefix", "student_id_nursery_pattern"),
            "Primary": ("student_id_primary_prefix", "student_id_primary_pattern"),
            "JHS": ("student_id_jhs_prefix", "student_id_jhs_pattern"),
        }
        prefix_field, pattern_field = division_fields[division]
        prefix = getattr(school, prefix_field).strip().upper()
        pattern = getattr(school, pattern_field)
        patterns = {
            "DIVISION_SEQUENCE": "{division}-{seq:04d}",
            "DIVISION_YEAR_SEQUENCE": "{division}-{year}-{seq:04d}",
            "SCHOOL_DIVISION_SEQUENCE": "{school}-{division}-{seq:04d}",
            "SCHOOL_DIVISION_YEAR_SEQUENCE": "{school}-{division}-{year}-{seq:04d}",
        }
        template = patterns[pattern]
        sequence, _ = StudentIDSequence.objects.get_or_create(
            school=school,
            division=division,
        )
        sequence = StudentIDSequence.objects.select_for_update().get(pk=sequence.pk)
        number = sequence.last_number
        year = timezone.localdate().year
        while True:
            number += 1
            username = template.format(
                school=f"S{school.pk}", division=prefix, year=year, seq=number
            )
            if not UserModel.objects.filter(username=username).exists():
                sequence.last_number = number
                sequence.save(update_fields=["last_number"])
                return username

    # Legacy fallback for callers that do not have a school/division context.
    registered_year = timezone.localdate().year
    counter = UserModel.objects.filter(is_student=True).count() + 1
    while True:
        username = f"{settings.STUDENT_ID_PREFIX}-{registered_year}-{counter}"
        if not UserModel.objects.filter(username=username).exists():
            return username
        counter += 1


def generate_lecturer_id():
    # Generate a username based on first and last name and registration date
    registered_year = datetime.now().strftime("%Y")
    
    # Start checking from 1 upwards to find the first available slot
    counter = 1
    while True:
        username = f"{settings.LECTURER_ID_PREFIX}-{registered_year}-{counter}"
        if not get_user_model().objects.filter(username=username).exists():
            return username
        counter += 1


def generate_student_credentials(school=None, division=None):
    return generate_student_id(school=school, division=division), generate_password()


def generate_lecturer_credentials():
    return generate_lecturer_id(), generate_password()


def generate_parent_credentials():
    registered_year = datetime.now().strftime("%Y")
    counter = 1
    while True:
        username = f"PAR-{registered_year}-{counter}"
        if not get_user_model().objects.filter(username=username).exists():
            return username, generate_password()
        counter += 1


class EmailThread(threading.Thread):
    def __init__(self, subject, recipient_list, template_name, context):
        self.subject = subject
        self.recipient_list = recipient_list
        self.template_name = template_name
        self.context = context
        threading.Thread.__init__(self)

    def run(self):
        try:
            send_html_email(
                subject=self.subject,
                recipient_list=self.recipient_list,
                template=self.template_name,
                context=self.context,
            )
        except Exception:
            # Threads used to swallow delivery errors completely, which made
            # registration look successful even when no email was sent.
            logger.exception(
                "Failed to send account email to %s",
                ", ".join(self.recipient_list),
            )


def send_new_account_email(user, password):
    if not user.email:
        logger.warning(
            "Skipping account email for %s: no email address on file",
            user.username,
        )
        return

    if user.is_student:
        template_name = "accounts/email/new_student_account_confirmation.html"
    elif user.is_parent:
        template_name = "accounts/email/new_parent_account_confirmation.html"
    else:
        template_name = "accounts/email/new_lecturer_account_confirmation.html"

    school = user.school
    school_name = school.name if school else "Scolaa"
    login_url = f"{settings.SITE_URL}{reverse('login')}"

    email = {
        "subject": f"Your {school_name} account confirmation and credentials",
        "recipient_list": [user.email],
        "template_name": template_name,
        "context": {
            "user": user,
            "password": password,
            "school": school,
            "login_url": login_url,
        },
    }
    EmailThread(**email).start()


# ########################################################
# Division-based Access Control Utilities
# ########################################################

def get_division_for_level(level_code):
    """
    Returns the division that a given level belongs to
    
    Args:
        level_code: The level code (e.g., 'Primary 1', 'JHS 1')
    
    Returns:
        Division constant (DIVISION_NURSERY, DIVISION_PRIMARY, or DIVISION_JHS) or None
    """
    for division, levels in settings.DIVISION_LEVEL_MAPPING.items():
        if level_code in levels:
            return division
    return None


def get_levels_for_division(division):
    """
    Returns all levels in a given division
    
    Args:
        division: Division constant (DIVISION_NURSERY, DIVISION_PRIMARY, or DIVISION_JHS)
    
    Returns:
        List of level codes in that division
    """
    return settings.DIVISION_LEVEL_MAPPING.get(division, [])


def check_teacher_division_access(teacher, level_code):
    """
    Validates if a teacher can access a given level based on their division
    
    Args:
        teacher: User object (must be a teacher)
        level_code: The level code to check access for
    
    Returns:
        Boolean indicating if teacher can access the level
    """
    # Use the User model's built-in method
    return teacher.can_access_level(level_code)


def filter_levels_by_division(user):
    """
    Filter LEVEL_CHOICES based on user's division
    
    Args:
        user: User object
    
    Returns:
        Filtered list of (code, name) tuples for levels the user can access
    """
    # Admins see all levels
    if user.is_superuser or user.is_school_admin:
        return settings.LEVEL_CHOICES
    
    # Teachers see only levels in their division
    if (user.is_teacher or user.is_lecturer) and user.division:
        accessible_levels = user.get_division_levels()
        return [(code, name) for code, name in settings.LEVEL_CHOICES if code in accessible_levels]
    
    # Default: return all levels
    return settings.LEVEL_CHOICES

