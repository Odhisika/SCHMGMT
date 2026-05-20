from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from school.models import School
from superadmin.forms import SchoolCreationForm

User = get_user_model()


class SchoolCreationFormTests(TestCase):
    def test_form_does_not_expose_subdomain_and_generates_internal_identifiers(self):
        form = SchoolCreationForm(data={
            "name": "Example Academy",
            "email": "admin@school.test",
            "phone": "+233000000000",
            "address": "Accra",
            "website": "https://school.test",
            "custom_domain": "",
            "primary_color": "#007bff",
            "secondary_color": "#6c757d",
            "is_active": "on",
        })

        self.assertNotIn("subdomain", form.fields)
        self.assertTrue(form.is_valid(), form.errors)

        school = form.save()

        self.assertEqual(school.slug, "example-academy")
        self.assertEqual(school.subdomain, "example-academy")


class SuperadminAccessTests(TestCase):
    @override_settings(
        ALLOWED_HOSTS=["admin.example.test"],
        PUBLIC_DOMAINS=["app.example.test"],
        MASTER_DOMAINS=["admin.example.test"],
    )
    def test_non_superuser_redirects_to_login_page_not_root_loop(self):
        school = School.objects.create(name="Example Academy")
        user = User.objects.create_user(
            username="school_admin",
            password="password",
            is_school_admin=True,
            school=school,
        )
        self.client.force_login(user)

        response = self.client.get("/", HTTP_HOST="admin.example.test")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/accounts/login/?next=/")

    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_superadmin_dashboard_is_available_on_shared_public_host(self):
        user = User.objects.create_superuser(
            username="root",
            email="root@example.test",
            password="password",
        )
        self.client.force_login(user)

        response = self.client.get("/superadmin/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Super Admin Dashboard")
