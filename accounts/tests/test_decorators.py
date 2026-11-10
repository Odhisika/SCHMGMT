from django.contrib.auth import get_user_model
from django.contrib.messages.storage.cookie import CookieStorage
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from accounts.decorators import admin_required, lecturer_required, student_required

User = get_user_model()


class MessageRequestMixin:
    """Attach message storage to RequestFactory requests.

    The access-control decorators call ``messages.error`` before redirecting,
    which needs ``MessageMiddleware`` (or at least message storage) on the
    request. ``RequestFactory`` requests do not run middleware, so attach a
    fallback storage explicitly.
    """

    def make_request(self, path="/restricted-view/"):
        request = self.factory.get(path)
        request._messages = CookieStorage(request)
        return request


class AdminRequiredDecoratorTests(MessageRequestMixin, TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )
        self.user = User.objects.create_user(
            username="user", email="user@example.com", password="password"
        )
        self.factory = RequestFactory()

    def admin_view(self, request):
        return HttpResponse("Admin View Content")

    def test_admin_required_decorator_redirects(self):
        decorated_view = admin_required(self.admin_view)

        request = self.make_request()
        request.user = self.user
        response = decorated_view(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_admin_required_decorator_redirects_to_correct_path(self):
        decorated_view = admin_required(function=self.admin_view, redirect_to="/login/")

        request = self.make_request()
        request.user = self.user
        response = decorated_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_admin_required_decorator_does_not_redirect_superuser(self):
        decorated_view = admin_required(self.admin_view)

        request = self.make_request()
        request.user = self.superuser
        response = decorated_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Admin View Content")

    def test_admin_redirect_decorator_return_correct_response(self):
        decorated_view = admin_required(self.admin_view)

        request = self.make_request()
        request.user = self.superuser
        response = decorated_view(request)
        self.assertIsInstance(response, HttpResponse)

    def test_school_admin_is_allowed(self):
        school_admin = User.objects.create_user(
            username="school_admin",
            email="school_admin@example.com",
            password="password",
            is_school_admin=True,
        )
        decorated_view = admin_required(self.admin_view)

        request = self.make_request()
        request.user = school_admin
        response = decorated_view(request)

        self.assertEqual(response.status_code, 200)

    def test_inactive_admin_is_denied(self):
        self.superuser.is_active = False
        self.superuser.save(update_fields=["is_active"])
        decorated_view = admin_required(self.admin_view)

        request = self.make_request()
        request.user = self.superuser
        response = decorated_view(request)

        self.assertEqual(response.status_code, 302)


class LecturerRequiredDecoratorTests(MessageRequestMixin, TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            username="lecturer",
            email="lecturer@example.com",
            password="password",
            is_lecturer=True,
        )
        self.user = User.objects.create_user(
            username="user", email="user@example.com", password="password"
        )
        self.factory = RequestFactory()

    def lecturer_view(self, request):
        return HttpResponse("Lecturer View Content")

    def test_lecturer_required_decorator_redirects(self):
        decorated_view = lecturer_required(self.lecturer_view)

        request = self.make_request()
        request.user = self.user

        response = decorated_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_lecturer_required_decorator_redirects_to_correct_path(self):
        decorated_view = lecturer_required(
            function=self.lecturer_view, redirect_to="/login/"
        )

        request = self.make_request()
        request.user = self.user

        response = decorated_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_lecturer_required_decorator_does_not_redirect_lecturer(self):
        decorated_view = lecturer_required(self.lecturer_view)

        request = self.make_request()
        request.user = self.lecturer

        response = decorated_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Lecturer View Content")

    def test_lecturer_redirect_decorator_return_correct_response(self):
        decorated_view = lecturer_required(self.lecturer_view)

        request = self.make_request()
        request.user = self.lecturer
        response = decorated_view(request)
        self.assertIsInstance(response, HttpResponse)

    def test_class_teacher_is_allowed(self):
        class_teacher = User.objects.create_user(
            username="class_teacher",
            email="class_teacher@example.com",
            password="password",
            is_teacher=True,
            is_class_teacher=True,
        )
        decorated_view = lecturer_required(self.lecturer_view)

        request = self.make_request()
        request.user = class_teacher
        response = decorated_view(request)

        self.assertEqual(response.status_code, 200)


class StudentRequiredDecoratorTests(MessageRequestMixin, TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student",
            email="student@example.com",
            password="password",
            is_student=True,
        )
        self.user = User.objects.create_user(
            username="user", email="user@example.com", password="password"
        )
        self.factory = RequestFactory()

    def student_view(self, request):
        return HttpResponse("Student View Content")

    def test_student_required_decorator_redirects(self):
        decorated_view = student_required(self.student_view)

        request = self.make_request()
        request.user = self.user

        response = decorated_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_student_required_decorator_redirects_to_correct_path(self):
        decorated_view = student_required(
            function=self.student_view, redirect_to="/login/"
        )

        request = self.make_request()
        request.user = self.user

        response = decorated_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_student_required_decorator_does_not_redirect_student(self):
        decorated_view = student_required(self.student_view)

        request = self.make_request()
        request.user = self.student

        response = decorated_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Student View Content")

    def test_student_redirect_decorator_return_correct_response(self):
        decorated_view = student_required(self.student_view)

        request = self.make_request()
        request.user = self.student
        response = decorated_view(request)
        self.assertIsInstance(response, HttpResponse)
