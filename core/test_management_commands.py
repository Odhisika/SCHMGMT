"""Tests for the demo-data management commands."""

import os
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import User
from core.demo_data import DEMO_EMAIL_DOMAIN, DEMO_SCHOOL_SLUG
from school.models import School


def _fake_demo_data():
    return SimpleNamespace(
        school=SimpleNamespace(
            name="Demo School", slug=DEMO_SCHOOL_SLUG, subdomain="demo"
        ),
        current_term="Demo Term",
        courses={"Primary 1": [object()]},
        courses_by_term={"Primary 1": {"First": [object()]}},
        class_teachers={
            "Primary 1": SimpleNamespace(username="teacher.class.primary1")
        },
        teachers={"Primary": SimpleNamespace(username="teacher.primary")},
        students={
            "Primary 1": [
                SimpleNamespace(student=SimpleNamespace(username="student.primary1.1"))
            ]
        },
        parents={"Primary 1": SimpleNamespace(user=SimpleNamespace(username="parent.primary1"))},
        results=[],
        results_by_term={"First": []},
        quizzes=[],
    )


class SeedCommandFlushGuardTests(TestCase):
    def _run_flush(self, *extra_args):
        with patch(
            "core.management.commands.seed_demo_data.call_command"
        ) as flush_mock, patch(
            "core.management.commands.seed_demo_data.build_demo_data",
            return_value=_fake_demo_data(),
        ):
            call_command(
                "seed_demo_data",
                "--flush",
                *extra_args,
                stdout=StringIO(),
                stderr=StringIO(),
            )
        return flush_mock

    def _make_real_school(self):
        return School.objects.create(
            name="Real School", slug="real-school", subdomain="real"
        )

    def test_flush_refused_when_debug_is_false(self):
        with override_settings(DEBUG=False):
            with self.assertRaisesMessage(CommandError, "DEBUG=False"):
                self._run_flush()

    def test_flush_allowed_with_env_var_on_production(self):
        with override_settings(DEBUG=False), patch.dict(
            os.environ, {"SEED_ALLOW_FLUSH": "1"}
        ):
            flush_mock = self._run_flush()

        flush_mock.assert_called_once()
        self.assertEqual(flush_mock.call_args.args[0], "flush")

    def test_flush_refused_when_non_demo_school_exists(self):
        with override_settings(DEBUG=True):
            self._make_real_school()
            with self.assertRaisesMessage(CommandError, "non-demo school"):
                self._run_flush()

    def test_flush_refused_when_real_user_exists(self):
        with override_settings(DEBUG=True):
            User.objects.create_user(
                username="realadmin",
                email="admin@realschool.test",
                password="irrelevant",
            )
            with self.assertRaisesMessage(CommandError, "non-demo user"):
                self._run_flush()

    def test_force_bypasses_all_flush_guards(self):
        with override_settings(DEBUG=False):
            self._make_real_school()
            User.objects.create_user(
                username="realadmin",
                email="admin@realschool.test",
                password="irrelevant",
            )
            flush_mock = self._run_flush("--force")

        flush_mock.assert_called_once()

    def test_flush_allowed_on_demo_only_development_database(self):
        with override_settings(DEBUG=True):
            flush_mock = self._run_flush()

        flush_mock.assert_called_once()


class RemoveDemoDataCommandTests(TestCase):
    def setUp(self):
        self.demo_school = School.objects.create(
            name="Greenwood International School",
            slug=DEMO_SCHOOL_SLUG,
            subdomain="greenwood",
        )
        self.demo_admin = User.objects.create_user(
            username="admin",
            email=f"admin@{DEMO_EMAIL_DOMAIN}",
            password="irrelevant",
            school=self.demo_school,
        )
        self.demo_root = User.objects.create_superuser(
            username="root",
            email=f"root@{DEMO_EMAIL_DOMAIN}",
            password="irrelevant",
        )
        self.real_school = School.objects.create(
            name="Real School", slug="real-school", subdomain="real"
        )
        self.real_user = User.objects.create_user(
            username="realadmin",
            email="admin@realschool.test",
            password="irrelevant",
            school=self.real_school,
        )

    def test_dry_run_preserves_all_data(self):
        out = StringIO()

        call_command("remove_demo_data", "--dry-run", stdout=out)

        self.assertIn("Dry run", out.getvalue())
        self.assertTrue(School.objects.filter(slug=DEMO_SCHOOL_SLUG).exists())
        self.assertTrue(User.objects.filter(username="admin").exists())
        self.assertTrue(User.objects.filter(username="root").exists())
        self.assertTrue(User.objects.filter(username="realadmin").exists())

    def test_removes_demo_data_and_keeps_real_data(self):
        out = StringIO()

        call_command("remove_demo_data", "--no-input", stdout=out)

        self.assertIn("Demo data removed", out.getvalue())
        self.assertFalse(School.objects.filter(slug=DEMO_SCHOOL_SLUG).exists())
        self.assertFalse(User.objects.filter(username="admin").exists())
        self.assertFalse(User.objects.filter(username="root").exists())
        self.assertTrue(School.objects.filter(slug="real-school").exists())
        self.assertTrue(User.objects.filter(username="realadmin").exists())

    def test_confirmation_can_abort_deletion(self):
        with patch("builtins.input", return_value="no"):
            with self.assertRaisesMessage(CommandError, "Aborted"):
                call_command("remove_demo_data", stdout=StringIO(), stderr=StringIO())

        self.assertTrue(School.objects.filter(slug=DEMO_SCHOOL_SLUG).exists())
        self.assertTrue(User.objects.filter(username="root").exists())

    def test_reports_when_no_demo_data_exists(self):
        self.demo_school.delete()
        self.demo_root.delete()
        out = StringIO()

        call_command("remove_demo_data", "--no-input", stdout=out)

        self.assertIn("No demo data found", out.getvalue())
        self.assertTrue(School.objects.filter(slug="real-school").exists())
        self.assertTrue(User.objects.filter(username="realadmin").exists())
