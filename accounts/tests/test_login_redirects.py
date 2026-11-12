from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

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
