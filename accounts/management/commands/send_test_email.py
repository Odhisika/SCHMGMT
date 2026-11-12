"""Send a real test email using the project's configured mail settings.

Usage:
    python manage.py send_test_email you@example.com
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email to verify SMTP/email delivery settings."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Recipient email address")

    def handle(self, *args, **options):
        recipient = options["email"]
        if not recipient:
            raise CommandError("A recipient email address is required.")

        self.stdout.write(f"Backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"From: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"To: {recipient}")

        send_mail(
            subject="SCHMGMT test email",
            message=(
                "This is a test email from your school management system.\n\n"
                "If you received this, your email settings are working."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )

        self.stdout.write(self.style.SUCCESS("Test email sent successfully."))
