"""Shared helpers for the project's automated test-suite.

The helpers build a small but realistic slice of the demo dataset (the same
builder used by ``manage.py seed_demo_data``) so integration tests exercise the
same relational graph that developers interact with in a seeded database.
"""

from __future__ import annotations

from django.conf import settings
from django.test import TestCase

from core.demo_data import build_demo_data


SMALL_LEVELS = ["Primary 1", "JHS 1"]


class DemoDataTestCase(TestCase):
    """Mixin that builds the demo dataset once per ``TestCase`` class.

    Subclasses can override the class attributes to trade coverage for speed.
    ``setUpTestData`` runs inside a class-level transaction, so the data is
    shared by every test method and rolled back when the class finishes.
    """

    demo_levels = SMALL_LEVELS
    demo_students_per_level = 2
    demo_attendance_days = 3
    demo_timetable = True
    demo_quizzes = True
    demo_resources = True

    @classmethod
    def setUpTestData(cls):
        cls.demo = build_demo_data(
            levels=cls.demo_levels,
            students_per_level=cls.demo_students_per_level,
            attendance_days=cls.demo_attendance_days,
            timetable=cls.demo_timetable,
            quizzes=cls.demo_quizzes,
            resources=cls.demo_resources,
            seed=42,
        )
        cls.school = cls.demo.school
        cls.admin = cls.demo.admin
        cls.superuser = cls.demo.superuser
        cls.teacher = cls.demo.teachers[settings.DIVISION_PRIMARY]
        cls.jhs_teacher = cls.demo.teachers[settings.DIVISION_JHS]
        cls.class_teacher = cls.demo.class_teacher
        cls.student = cls.demo.students[cls.demo_levels[0]][0]
        cls.student_user = cls.student.student
        cls.parent = cls.demo.parents[cls.demo_levels[0]]
        cls.parent_user = cls.parent.user
        cls.primary_course = cls.demo.courses[cls.demo_levels[0]][0]
        cls.jhs_course = cls.demo.courses[cls.demo_levels[1]][0]
        cls.result = cls.demo.results[0]
        cls.current_term = cls.demo.current_term
