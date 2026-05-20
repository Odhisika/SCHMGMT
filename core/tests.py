from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

User = get_user_model()


class PublicSidebarTests(TestCase):
    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_superuser_can_open_public_home_without_superadmin_namespace_error(self):
        user = User.objects.create_superuser(
            username="root",
            email="root@example.test",
            password="password",
        )
        self.client.force_login(user)

        response = self.client.get("/en/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Super Admin Dashboard")
