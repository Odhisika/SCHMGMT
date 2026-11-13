from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from school.models import School

User = get_user_model()


class LoginRedirectTests(TestCase):
    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    )
    def test_temporary_password_login_redirects_to_password_change(self):
        User.objects.create_user(
            username="new.student",
            password="Temporary123!",
            must_change_password=True,
        )

        response = self.client.post(
            "/en/accounts/login/",
            {"username": "new.student", "password": "Temporary123!"},
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/en/accounts/change_password/")

    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    )
    def test_superuser_shared_login_redirects_to_superadmin_dashboard(self):
        User.objects.create_superuser(
            username="root",
            email="root@example.test",
            password="password",
        )

        response = self.client.post(
            "/en/accounts/login/",
            {"username": "root", "password": "password"},
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/superadmin/")

    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    )
    def test_authenticated_user_visiting_login_is_sent_back_into_app(self):
        school = School.objects.create(name="Redirect Academy")
        user = User.objects.create_user(
            username="student.one",
            password="Password123!",
            school=school,
        )
        self.client.force_login(user)

        response = self.client.get("/en/accounts/login/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/en/")

    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    )
    def test_logout_flushes_session_and_redirects_to_login(self):
        school = School.objects.create(name="Logout Academy")
        user = User.objects.create_user(
            username="student.two",
            password="Password123!",
            school=school,
        )
        self.client.force_login(user)
        session = self.client.session
        session["marker"] = "still-here"
        session.save()

        response = self.client.get("/en/accounts/logout/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/en/accounts/login/")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.cookies["sessionid"].value, "")
