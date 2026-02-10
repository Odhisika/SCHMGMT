import threading
from datetime import datetime
from django.contrib.auth import get_user_model
from django.conf import settings
from core.utils import send_html_email


def generate_password():
    return get_user_model().objects.make_random_password()


def generate_student_id():
    # Generate a username based on first and last name and registration date
    registered_year = datetime.now().strftime("%Y")
    students_count = get_user_model().objects.filter(is_student=True).count()
    username = f"{settings.STUDENT_ID_PREFIX}-{registered_year}-{students_count}"
    
    # Ensure uniqueness
    counter = students_count
    while get_user_model().objects.filter(username=username).exists():
        counter += 1
        username = f"{settings.STUDENT_ID_PREFIX}-{registered_year}-{counter}"
    
    return username


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


def generate_student_credentials():
    return generate_student_id(), generate_password()


def generate_lecturer_credentials():
    return generate_lecturer_id(), generate_password()


class EmailThread(threading.Thread):
    def __init__(self, subject, recipient_list, template_name, context):
        self.subject = subject
        self.recipient_list = recipient_list
        self.template_name = template_name
        self.context = context
        threading.Thread.__init__(self)

    def run(self):
        send_html_email(
            subject=self.subject,
            recipient_list=self.recipient_list,
            template=self.template_name,
            context=self.context,
        )


def send_new_account_email(user, password):
    if user.is_student:
        template_name = "accounts/email/new_student_account_confirmation.html"
    else:
        template_name = "accounts/email/new_lecturer_account_confirmation.html"
    email = {
        "subject": "Your SkyLearn account confirmation and credentials",
        "recipient_list": [user.email],
        "template_name": template_name,
        "context": {"user": user, "password": password},
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

