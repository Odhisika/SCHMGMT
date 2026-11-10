"""Tests for the super-admin portal: access control and school provisioning."""

from django.urls import reverse

from accounts.models import User
from core.testing import DemoDataTestCase
from school.models import School


class SuperAdminAccessTests(DemoDataTestCase):
    def test_superuser_can_open_dashboard_and_lists(self):
        self.client.force_login(self.superuser)

        dashboard = self.client.get(reverse("superadmin:dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["total_schools"], 1)
        self.assertGreaterEqual(dashboard.context["total_students"], 1)

        self.assertEqual(
            self.client.get(reverse("superadmin:school_list")).status_code, 200
        )

    def test_non_superuser_is_redirected_to_login(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("superadmin:dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_school_detail_renders_counts(self):
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("superadmin:school_detail", args=[self.school.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["school"], self.school)
        self.assertGreaterEqual(response.context["students_count"], 1)


class SchoolProvisioningTests(DemoDataTestCase):
    def test_school_creation_form_renders(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("superadmin:school_create"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("school_form", response.context)
        self.assertIn("admin_form", response.context)

    def test_creating_school_also_creates_its_admin(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("superadmin:school_create"),
            {
                "name": "Riverside Preparatory",
                "email": "info@riverside.test",
                "phone": "+233200000999",
                "address": "1 River Road",
                "website": "https://riverside.test",
                "custom_domain": "",
                "primary_color": "#123456",
                "secondary_color": "#654321",
                "is_active": "on",
                "username": "riverside.admin",
                "first_name": "River",
                "last_name": "Admin",
                "password1": "Str0ng-Passw0rd!",
                "password2": "Str0ng-Passw0rd!",
            },
        )

        school = School.objects.get(name="Riverside Preparatory")
        admin = User.objects.get(username="riverside.admin")

        self.assertRedirects(
            response, reverse("superadmin:school_detail", args=[school.pk])
        )
        self.assertEqual(admin.school, school)
        self.assertTrue(admin.is_school_admin)
        self.assertTrue(admin.is_staff)

    def test_toggle_active_flips_school_status(self):
        self.client.force_login(self.superuser)
        self.assertTrue(self.school.is_active)

        response = self.client.post(
            reverse("superadmin:school_toggle_active", args=[self.school.pk])
        )

        self.assertRedirects(
            response, reverse("superadmin:school_detail", args=[self.school.pk])
        )
        self.school.refresh_from_db()
        self.assertFalse(self.school.is_active)
