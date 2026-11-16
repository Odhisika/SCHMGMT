"""Tenant-isolation tests for the in-app notification center."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.models import Notification
from core.notifications import mark_all_read, notify, unread_count, visible_notifications
from school.models import School


class NotificationTenantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(name="Notification School A")
        cls.school_b = School.objects.create(name="Notification School B")
        cls.admin_a = User.objects.create_user(
            username="notification-admin-a",
            password="test-pass",
            school=cls.school_a,
            is_school_admin=True,
        )
        cls.admin_b = User.objects.create_user(
            username="notification-admin-b",
            password="test-pass",
            school=cls.school_b,
            is_school_admin=True,
        )

    def setUp(self):
        self.notice_a = notify(
            self.school_a,
            "School A notice",
            audience=Notification.AUDIENCE_ADMIN,
        )
        self.notice_b = notify(
            self.school_b,
            "School B notice",
            audience=Notification.AUDIENCE_ADMIN,
        )
        self.client.force_login(self.admin_a)

    def test_visible_notifications_are_limited_to_the_current_school(self):
        visible = visible_notifications(self.admin_a, self.school_a)

        self.assertIn(self.notice_a, visible)
        self.assertNotIn(self.notice_b, visible)
        self.assertEqual(unread_count(self.admin_a, self.school_a), 1)

    def test_notification_list_does_not_render_other_school_notices(self):
        response = self.client.get(reverse("notification_list"), {"filter": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "School A notice")
        self.assertNotContains(response, "School B notice")

    def test_opening_another_schools_notification_returns_not_found(self):
        response = self.client.get(
            reverse("notification_open", args=[self.notice_b.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_mark_all_read_only_marks_the_current_school(self):
        mark_all_read(self.admin_a, self.school_a)

        self.assertTrue(self.notice_a.read_by.filter(pk=self.admin_a.pk).exists())
        self.assertFalse(self.notice_b.read_by.filter(pk=self.admin_a.pk).exists())

    def test_notify_rejects_a_recipient_from_another_school(self):
        result = notify(
            self.school_a,
            "Cross-school personal notice",
            recipient=self.admin_b,
        )

        self.assertIsNone(result)
        self.assertFalse(
            Notification.objects.filter(title="Cross-school personal notice").exists()
        )

    def test_notify_rejects_an_actor_from_another_school(self):
        result = notify(
            self.school_a,
            "Cross-school actor notice",
            audience=Notification.AUDIENCE_ADMIN,
            actor=self.admin_b,
        )

        self.assertIsNone(result)
        self.assertFalse(
            Notification.objects.filter(title="Cross-school actor notice").exists()
        )

    def test_notify_without_a_school_is_not_created(self):
        result = notify(None, "Orphan notice")

        self.assertIsNone(result)
        self.assertFalse(Notification.objects.filter(title="Orphan notice").exists())

    def test_model_validation_rejects_cross_school_people(self):
        notification = Notification(
            school=self.school_a,
            recipient=self.admin_b,
            title="Invalid recipient",
        )

        with self.assertRaises(ValidationError):
            notification.full_clean()

    def test_database_requires_a_school(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    title="No school",
                    audience=Notification.AUDIENCE_ADMIN,
                )
