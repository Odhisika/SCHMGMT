from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

User = get_user_model()


class GlobalLoadingAssetsTests(TestCase):
    """The shared button-loading assets must be present in every portal."""

    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    )
    def test_login_page_loads_global_loading_assets(self):
        response = self.client.get("/en/accounts/login/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/button-loading.js")
        self.assertContains(response, "css/loading-states.css")
        self.assertContains(response, "data-loading-text")

    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    )
    def test_superadmin_layout_loads_global_loading_assets(self):
        user = User.objects.create_superuser(
            username="loading.root",
            email="loading.root@example.test",
            password="password",
        )
        self.client.force_login(user)

        response = self.client.get("/superadmin/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/button-loading.js")
        self.assertContains(response, "css/loading-states.css")
