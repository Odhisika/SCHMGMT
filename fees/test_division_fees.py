from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import STUDENT_STATUS_ACTIVE, Student
from core.models import Term
from school.models import School, SchoolDivision, SchoolDivisionLevel

from .forms import FeeStructureForm
from .models import FeeItem, FeeStructure, StudentFeeAssignment

User = get_user_model()


class DivisionFeeAssignmentTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Fee Academy", slug="fee-academy", subdomain="fee"
        )
        self.creche = SchoolDivision.objects.create(
            school=self.school, name="Creche", id_prefix="CRE", order=0
        )
        # Use the same lowercase/double-space wording as the live school data.
        SchoolDivisionLevel.objects.create(
            division=self.creche, name="creche  1", order=0
        )
        SchoolDivisionLevel.objects.create(
            division=self.creche, name="creche 2", order=1
        )

        self.term = Term.objects.create(
            school=self.school, term="Third", year="2026", is_current_term=True
        )

        self.admin = User.objects.create_user(
            username="fee-admin",
            password="password",
            school=self.school,
            is_school_admin=True,
        )
        self.student_one_user = User.objects.create_user(
            username="creche-one",
            password="password",
            school=self.school,
            first_name="Ama",
            last_name="One",
            is_student=True,
        )
        self.student_two_user = User.objects.create_user(
            username="creche-two",
            password="password",
            school=self.school,
            first_name="Kofi",
            last_name="Two",
            is_student=True,
        )
        self.student_one = Student.objects.create(
            student=self.student_one_user,
            level="creche  1",
            status=STUDENT_STATUS_ACTIVE,
        )
        self.student_two = Student.objects.create(
            student=self.student_two_user,
            level="creche 2",
            status=STUDENT_STATUS_ACTIVE,
        )

    def make_fee(self, **kwargs):
        defaults = {
            "school": self.school,
            "name": "Creche third term fees",
            "term": "Third",
            "amount": Decimal("0.00"),
            "auto_assign": True,
            "is_active": True,
        }
        defaults.update(kwargs)
        fee = FeeStructure.objects.create(**defaults)
        FeeItem.objects.create(fee_structure=fee, name="Tuition", amount=Decimal("950.00"))
        fee.update_total_amount()
        fee.refresh_from_db()
        return fee

    def assignments_for(self, student):
        return StudentFeeAssignment.objects.filter(student=student)

    def test_single_class_fee_assigns_and_appears_for_student(self):
        fee = self.make_fee(level="creche  1")

        self.assertEqual(self.assignments_for(self.student_one).count(), 1)
        self.assertEqual(self.assignments_for(self.student_two).count(), 0)
        assignment = self.assignments_for(self.student_one).get()
        self.assertEqual(assignment.amount, Decimal("950.00"))
        self.assertEqual(assignment.term, self.term)

        self.client.force_login(self.student_one_user)
        response = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Creche third term fees")
        self.assertContains(response, "950.00")

    def test_division_wide_fee_assigns_every_student_in_every_class(self):
        fee = self.make_fee(division="Creche", level="")

        for student in (self.student_one, self.student_two):
            assignment = self.assignments_for(student).get()
            self.assertEqual(assignment.fee_structure, fee)
            self.assertEqual(assignment.amount, Decimal("950.00"))

    def test_fee_form_offers_division_wide_scope(self):
        form = FeeStructureForm(
            school=self.school,
            data={
                "name": "Whole division fee",
                "division": "Creche",
                "level": "",
                "term": "Third",
                "auto_assign": "on",
                "is_active": "on",
            },
        )
        self.assertTrue(form.is_valid(), form.errors)

        form = FeeStructureForm(
            school=self.school,
            data={
                "name": "Bad scope",
                "division": "Creche",
                "level": "JHS 1",
                "term": "Third",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("level", form.errors)

    def test_editing_scope_adds_assignments_for_new_classes(self):
        fee = self.make_fee(level="creche  1")
        self.assertEqual(self.assignments_for(self.student_two).count(), 0)

        fee.division = "Creche"
        fee.level = ""
        fee.save()

        self.assertEqual(self.assignments_for(self.student_two).count(), 1)
        self.assertEqual(
            self.assignments_for(self.student_two).get().amount,
            Decimal("950.00"),
        )

    def test_manual_amount_override_is_not_clobbered(self):
        fee = self.make_fee(level="creche  1")
        assignment = self.assignments_for(self.student_one).get()
        assignment.amount = Decimal("100.00")
        assignment.save(update_fields=["amount"])

        FeeItem.objects.create(fee_structure=fee, name="Exam", amount=Decimal("50.00"))
        fee.update_total_amount()

        assignment.refresh_from_db()
        self.assertEqual(assignment.amount, Decimal("100.00"))
