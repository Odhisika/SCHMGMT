from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import STUDENT_STATUS_ACTIVE, Student
from school.division_utils import get_division_choices, get_level_choices
from school.forms import SchoolDivisionOrderForm
from school.models import (
    School,
    SchoolDivision,
    SchoolDivisionLevel,
    SchoolDivisionOrder,
)

User = get_user_model()


class DivisionOrderingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Division Academy", slug="division-academy", subdomain="division"
        )
        self.creche = SchoolDivision.objects.create(
            school=self.school,
            name="Creche",
            id_prefix="CRE",
            order=0,
        )
        SchoolDivisionLevel.objects.create(division=self.creche, name="Creche 1", order=0)
        SchoolDivisionLevel.objects.create(division=self.creche, name="Creche 2", order=1)

    def division_names(self):
        return [name for name, _ in get_division_choices(self.school)]

    def level_names(self):
        return [code for code, _ in get_level_choices(self.school)]

    def test_custom_divisions_default_to_the_front(self):
        self.assertEqual(
            self.division_names(), ["Creche", "Nursery", "Primary", "JHS"]
        )
        self.assertEqual(self.level_names()[:2], ["Creche 1", "Creche 2"])

    def test_saved_order_controls_divisions_and_levels(self):
        for name, order in (
            ("Nursery", 0),
            ("Primary", 1),
            ("Creche", 2),
            ("JHS", 3),
        ):
            SchoolDivisionOrder.objects.create(
                school=self.school, division=name, order=order
            )

        self.assertEqual(
            self.division_names(), ["Nursery", "Primary", "Creche", "JHS"]
        )
        self.assertEqual(self.level_names()[:4], [
            "Nursery 1", "Nursery 2", "KG 1", "KG 2",
        ])

    def test_order_form_sorts_by_submitted_numbers(self):
        form = SchoolDivisionOrderForm(
            school=self.school,
            data={"order_0": 3, "order_1": 2, "order_2": 1, "order_3": 0},
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.ordered_divisions(), ["JHS", "Primary", "Nursery", "Creche"]
        )

    def test_order_form_rejects_duplicate_numbers(self):
        form = SchoolDivisionOrderForm(
            school=self.school,
            data={"order_0": 0, "order_1": 0, "order_2": 1, "order_3": 2},
        )

        self.assertFalse(form.is_valid())

    def test_school_admin_can_save_a_new_order(self):
        admin = User.objects.create_user(
            username="division-admin",
            password="password",
            school=self.school,
            is_school_admin=True,
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("school_settings_divisions"),
            {
                "action": "save_order",
                "order_0": 2,  # Creche
                "order_1": 1,  # Nursery
                "order_2": 0,  # Primary
                "order_3": 3,  # JHS
            },
        )

        self.assertRedirects(response, reverse("school_settings_divisions"))
        self.assertEqual(
            self.division_names(), ["Primary", "Nursery", "Creche", "JHS"]
        )

    def test_settings_and_dashboard_render_the_ordered_divisions(self):
        admin = User.objects.create_user(
            username="ordered-admin",
            password="password",
            school=self.school,
            is_school_admin=True,
        )
        self.client.force_login(admin)

        settings_page = self.client.get(reverse("school_settings_divisions"))
        self.assertEqual(settings_page.status_code, 200)
        html = settings_page.content.decode()
        self.assertLess(html.index("Creche"), html.index("Nursery"))

        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(
            [name for name, _ in dashboard.context["divisions"]],
            ["Creche", "Nursery", "Primary", "JHS"],
        )


class CustomDivisionEverywhereTests(TestCase):
    """A school-defined division must show up on every division screen."""

    def setUp(self):
        self.school = School.objects.create(
            name="Creche Academy", slug="creche-academy", subdomain="creche"
        )
        self.creche = SchoolDivision.objects.create(
            school=self.school,
            name="Creche",
            id_prefix="CRE",
            order=0,
        )
        SchoolDivisionLevel.objects.create(division=self.creche, name="Creche 1", order=0)
        SchoolDivisionLevel.objects.create(division=self.creche, name="Creche 2", order=1)

        self.admin = User.objects.create_user(
            username="creche-admin",
            password="password",
            school=self.school,
            is_school_admin=True,
        )
        self.client.force_login(self.admin)

    def assert_creche_offered(self, url, context_key="divisions"):
        response = self.client.get(reverse(url))
        self.assertEqual(response.status_code, 200, url)
        names = [name for name, _ in response.context[context_key]]
        self.assertIn("Creche", names, url)
        return response

    def test_academics_screens_offer_creche(self):
        response = self.client.get(reverse("programs"))
        self.assertEqual(response.status_code, 200)
        creche_tab = response.context["division_tabs"][0]
        self.assertEqual(creche_tab["name"], "Creche")
        self.assertEqual(
            [code for code, _ in creche_tab["levels"]],
            ["Creche 1", "Creche 2"],
        )
        self.assertContains(
            response,
            reverse("class_level_detail", kwargs={"level_code": "Creche 1"}),
        )

        self.assert_creche_offered("course_allocation_view")
        self.assert_creche_offered("lesson_note_admin_list")
        self.assert_creche_offered("timetable:timetable_dashboard")

    def test_lesson_note_filter_finds_custom_division_records(self):
        from core.models import Term
        from course.models import Course, LessonNote, Program

        program = Program.objects.create(
            title="Creche Program", school=self.school, division="Creche"
        )
        term = Term.objects.create(term="First", year="2026", school=self.school)
        course = Course.objects.create(
            title="Creche Literacy",
            code="CRE101",
            program=program,
            level="Creche 1",
            term="First",
            school=self.school,
        )
        note = LessonNote.objects.create(
            teacher=self.admin,
            course=course,
            term=term,
            week_number=1,
            title="Creche Week 1",
            topic="Sounds",
            objectives="Recognise initial sounds.",
            content="Letter-sound activities.",
            methodology="Group work.",
            status="SUBMITTED",
        )

        response = self.client.get(
            reverse("lesson_note_admin_list"), {"division": "Creche"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(note, list(response.context["lesson_notes"]))
        self.assertEqual(
            [code for code, _ in response.context["current_division_levels"]],
            ["Creche 1", "Creche 2"],
        )

    def test_exams_and_results_screens_offer_creche(self):
        for url in (
            "create_promotion",
            "report_cards",
            "ca_scoresheet",
            "manage_scores",
        ):
            self.assert_creche_offered(url)

    def test_administration_screens_offer_creche(self):
        response = self.assert_creche_offered("fees:dashboard")
        self.assertEqual(response.context["divisions"][1][0], "Creche")
        self.assert_creche_offered("fees:defaulters_list")

    def test_forms_accept_and_save_custom_division_and_levels(self):
        from core.forms import NewsAndEventsForm
        from course.forms import CourseAddForm, ProgramForm
        from course.models import Program
        from fees.forms import FeeStructureForm
        from fees.models import FeeStructure
        from timetable.forms import PeriodForm
        from timetable.models import Period

        program_form = ProgramForm(
            data={
                "title": "Creche Program",
                "summary": "Early years",
                "school": self.school.pk,
                "division": "Creche",
                "is_academic_block": True,
            },
            school=self.school,
        )
        self.assertTrue(program_form.is_valid(), program_form.errors)
        program = program_form.save()
        self.assertEqual(program.division, "Creche")

        invalid_form = ProgramForm(
            data={
                "title": "Unknown Division",
                "summary": "",
                "school": self.school.pk,
                "division": "Not-A-School-Division",
                "is_academic_block": True,
            },
            school=self.school,
        )
        self.assertFalse(invalid_form.is_valid())

        course_form = CourseAddForm(
            data={
                "title": "Creche Literacy",
                "code": "CRE101",
                "summary": "",
                "level": "Creche 1",
                "is_core_subject": True,
            },
            school=self.school,
        )
        self.assertTrue(course_form.is_valid(), course_form.errors)
        course = course_form.save(commit=False)
        course.program = program
        course.term = "First"
        course.school = self.school
        course.save()
        self.assertEqual(course.level, "Creche 1")

        fee_form = FeeStructureForm(
            data={
                "name": "Creche Fees",
                "level": "Creche 1",
                "term": "First",
                "auto_assign": True,
                "description": "",
                "is_active": True,
            },
            school=self.school,
        )
        self.assertTrue(fee_form.is_valid(), fee_form.errors)
        fee = fee_form.save(commit=False)
        fee.school = self.school
        fee.save()
        self.assertEqual(fee.level, "Creche 1")
        self.assertEqual(FeeStructure.objects.get(pk=fee.pk).level, "Creche 1")

        period_form = PeriodForm(
            data={
                "division": "Creche",
                "name": "Period 1",
                "period_type": "LESSON",
                "start_time": "08:00",
                "end_time": "09:00",
                "order": 1,
            },
            school=self.school,
        )
        self.assertTrue(period_form.is_valid(), period_form.errors)
        period = period_form.save(commit=False)
        period.school = self.school
        period.save()
        self.assertEqual(Period.objects.get(pk=period.pk).division, "Creche")

        news_form = NewsAndEventsForm(
            data={
                "title": "Creche notice",
                "summary": "Welcome to Creche",
                "posted_as": "News",
                "target_division": "Creche",
                "target_role": "ALL",
            },
            school=self.school,
        )
        self.assertTrue(news_form.is_valid(), news_form.errors)
        news = news_form.save(commit=False)
        news.school = self.school
        news.save()
        self.assertEqual(news.target_division, "Creche")

    def test_assign_teacher_divisions_command_supports_custom_division(self):
        from django.core.management import call_command
        from io import StringIO

        from course.models import Program

        department = Program.objects.create(
            title="Creche Department", school=self.school, division="Creche"
        )
        teacher = User.objects.create_user(
            username="creche-teacher",
            password="password",
            school=self.school,
            department=department,
            is_teacher=True,
        )

        output = StringIO()
        call_command(
            "assign_teacher_divisions",
            "--auto",
            "--school",
            self.school.slug,
            stdout=output,
        )

        teacher.refresh_from_db()
        self.assertEqual(teacher.division, "Creche")

    def test_admin_formfields_accept_custom_values(self):
        from course.models import Program

        formfield = Program._meta.get_field("division").formfield()
        self.assertEqual(formfield.clean("Creche"), "Creche")

    def test_targeting_ajax_finds_students_in_custom_division(self):
        user = User.objects.create_user(
            username="creche-learner",
            password="password",
            school=self.school,
            first_name="Ama",
            last_name="Creche",
            is_student=True,
        )
        Student.objects.create(
            student=user,
            level="Creche 1",
            status=STUDENT_STATUS_ACTIVE,
        )

        response = self.client.get(
            reverse("get_users_for_targeting"),
            {"division": "Creche", "role": "STUDENTS"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ama Creche")
