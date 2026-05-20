from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from school.middleware import SchoolMiddleware
from school.models import School

User = get_user_model()


class SchoolMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SchoolMiddleware(lambda request: None)
        self.school = School.objects.create(
            name="Imperial Academy",
            slug="imperial-academy",
            subdomain="imp",
        )
        self.user = User.objects.create_user(
            username="imp_admin",
            password="password",
            school=self.school,
            is_school_admin=True,
        )

    def _request(self, host):
        request = self.factory.get("/", HTTP_HOST=host)
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        request.user = self.user
        return request

    @override_settings(
        MASTER_DOMAINS=["ssm.imperialacademy.edu.gh"],
        ENFORCE_SCHOOL_SUBDOMAIN_REDIRECTS=False,
    )
    def test_master_domain_uses_user_school_without_redirect_when_disabled(self):
        request = self._request("ssm.imperialacademy.edu.gh")

        response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertEqual(request.school, self.school)
        self.assertEqual(request.session["school_slug"], self.school.slug)

    @override_settings(
        MASTER_DOMAINS=["ssm.imperialacademy.edu.gh"],
        ENFORCE_SCHOOL_SUBDOMAIN_REDIRECTS=True,
    )
    def test_master_domain_redirects_to_school_subdomain_when_enabled(self):
        request = self._request("ssm.imperialacademy.edu.gh")

        response = self.middleware.process_request(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://imp.imperialacademy.edu.gh/")
