from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from accounts.utils import EmailThread, send_new_account_email


class FakeUser:
    def __init__(self, email="student@example.com", is_student=True):
        self.username = "STU-2026-1"
        self.email = email
        self.is_student = is_student
        self.first_name = "Test"
        self.last_name = "Student"
        self.school = None

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"


class AccountEmailTests(SimpleTestCase):
    @patch("accounts.utils.EmailThread")
    def test_email_includes_the_configured_login_link(self, thread_cls):
        user = FakeUser()

        send_new_account_email(user, "TempPass123!")

        thread_cls.assert_called_once()
        kwargs = thread_cls.call_args.kwargs
        self.assertEqual(kwargs["recipient_list"], [user.email])
        self.assertEqual(
            kwargs["context"]["login_url"],
            f"{settings.SITE_URL}{reverse('login')}",
        )
        thread_cls.return_value.start.assert_called_once()

    @patch("accounts.utils.EmailThread")
    def test_user_without_an_email_is_skipped(self, thread_cls):
        user = FakeUser(email="")

        send_new_account_email(user, "TempPass123!")

        thread_cls.assert_not_called()

    @patch(
        "accounts.utils.send_html_email",
        side_effect=Exception("SMTP rejected the sender"),
    )
    def test_delivery_errors_are_logged_instead_of_silently_swallowed(
        self, send_html_email
    ):
        thread = EmailThread(
            subject="Test",
            recipient_list=["student@example.com"],
            template_name="accounts/email/new_student_account_confirmation.html",
            context={},
        )

        with self.assertLogs("accounts.utils", level="ERROR"):
            thread.run()


class SendTestEmailCommandTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_command_sends_an_email_through_the_configured_backend(self):
        out = StringIO()

        call_command("send_test_email", "teacher@example.com", stdout=out)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["teacher@example.com"])
        self.assertEqual(message.from_email, settings.DEFAULT_FROM_EMAIL)
        self.assertIn("Test email sent successfully.", out.getvalue())
