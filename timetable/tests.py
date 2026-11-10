"""Tests for timetable periods, clash detection and access control."""

from datetime import time

from django.core.exceptions import ValidationError
from django.urls import reverse

from core.testing import DemoDataTestCase
from timetable.models import Period, TimetableEntry


class PeriodModelTests(DemoDataTestCase):
    def test_end_time_must_be_after_start_time(self):
        period = Period(
            school=self.school,
            name="Bad Period",
            period_type="LESSON",
            division="Primary",
            start_time=time(10, 0),
            end_time=time(10, 0),
            order=99,
        )

        with self.assertRaises(ValidationError):
            period.clean()

    def test_valid_period_passes_validation(self):
        period = Period(
            school=self.school,
            name="Good Period",
            period_type="LESSON",
            division="Primary",
            start_time=time(10, 0),
            end_time=time(10, 45),
            order=99,
        )

        period.full_clean()

    def test_string_contains_time_range(self):
        period = Period.objects.filter(school=self.school).first()
        self.assertIn("-", str(period))


class TimetableEntryModelTests(DemoDataTestCase):
    def test_teacher_conflict_is_detected(self):
        existing = TimetableEntry.objects.filter(
            school=self.school, term=self.current_term
        ).first()
        clash = TimetableEntry(
            school=self.school,
            term=self.current_term,
            level="Primary 2",
            day_of_week=existing.day_of_week,
            period=existing.period,
            subject=self.primary_course,
            teacher=existing.teacher,
        )

        with self.assertRaises(ValidationError) as error:
            clash.full_clean()

        self.assertIn("already assigned", str(error.exception))

    def test_different_teacher_does_not_conflict(self):
        existing = TimetableEntry.objects.filter(
            school=self.school, term=self.current_term
        ).first()
        entry = TimetableEntry(
            school=self.school,
            term=self.current_term,
            level="Primary 2",
            day_of_week=existing.day_of_week,
            period=existing.period,
            subject=self.primary_course,
            teacher=self.demo.dep_head,
        )

        entry.full_clean()

    def test_string_describes_slot_and_subject(self):
        entry = TimetableEntry.objects.filter(school=self.school).first()
        rendered = str(entry)

        self.assertIn(entry.period.name, rendered)
        self.assertIn(entry.subject.title, rendered)

    def test_free_period_string(self):
        existing = TimetableEntry.objects.filter(school=self.school).first()
        free = TimetableEntry(
            school=self.school,
            term=self.current_term,
            level="Primary 2",
            day_of_week=existing.day_of_week,
            period=existing.period,
            subject=None,
            teacher=None,
        )

        self.assertIn("Free Period", str(free))


class TimetableViewTests(DemoDataTestCase):
    def test_dashboard_renders_for_teacher_and_student(self):
        self.client.force_login(self.teacher)
        self.assertEqual(
            self.client.get(reverse("timetable:timetable_dashboard")).status_code,
            200,
        )

        self.client.force_login(self.student_user)
        self.assertEqual(
            self.client.get(reverse("timetable:timetable_dashboard")).status_code,
            200,
        )

    def test_class_timetable_enforces_level_access(self):
        self.client.force_login(self.student_user)

        own = self.client.get(
            reverse("timetable:timetable_by_class", args=[self.student.level])
        )
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.context["level"], self.student.level)

        other_level = self.demo_levels[1]
        denied = self.client.get(
            reverse("timetable:timetable_by_class", args=[other_level])
        )
        self.assertEqual(denied.status_code, 302)
        self.assertEqual(denied.url, reverse("timetable:timetable_dashboard"))

    def test_period_management_requires_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("timetable:period_list")).status_code, 200
        )

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("timetable:period_list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")
