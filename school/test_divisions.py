from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
