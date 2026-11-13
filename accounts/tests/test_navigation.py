from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from school.models import School

User = get_user_model()


class FullPageNavigationTests(TestCase):
    """The shared layout must not swap pages without their page scripts."""

    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    )
    def test_main_layout_does_not_boost_full_page_navigation(self):
        school = School.objects.create(name="Navigation Academy")
        user = User.objects.create_user(
            username="navigation.student",
            password="Password123!",
            school=school,
        )
        self.client.force_login(user)

        response = self.client.get("/en/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'hx-boost="true"')
        self.assertNotContains(response, 'hx-target="#main-content"')
        self.assertNotContains(response, 'hx-select="#main-content"')
