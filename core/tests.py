from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from school.models import School

User = get_user_model()


class PublicSidebarTests(TestCase):
    @override_settings(
        PUBLIC_DOMAINS=["localhost"],
        MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
        STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    )
    def test_superuser_can_open_public_home_with_superadmin_link_available(self):
        user = User.objects.create_superuser(
            username="root",
            email="root@example.test",
            password="password",
        )
        self.client.force_login(user)

        response = self.client.get("/en/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Super Admin Dashboard")


@override_settings(
    PUBLIC_DOMAINS=["localhost"],
    MASTER_DOMAINS=["admin.localhost", "127.0.0.1"],
    ENFORCE_SCHOOL_SUBDOMAIN_REDIRECTS=False,
)
class DashboardChartTests(TestCase):
    def test_chart_script_runs_after_chart_js_is_loaded(self):
        school = School.objects.create(
            name="Chart Academy", slug="chart-academy", subdomain="chart"
        )
        admin = User.objects.create_user(
            username="chart_admin",
            password="password",
            school=school,
            is_school_admin=True,
        )
        self.client.force_login(admin)

        response = self.client.get("/en/dashboard/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="dashboard-data-payload"', html)
        self.assertIn('"gender"', html)

        chart_js_pos = html.find("chart.js")
        init_pos = html.find("initDashboardCharts")
        self.assertNotEqual(chart_js_pos, -1)
        self.assertNotEqual(init_pos, -1)
        self.assertGreater(init_pos, chart_js_pos)
        self.assertNotIn("js/dashboard.js", html)
