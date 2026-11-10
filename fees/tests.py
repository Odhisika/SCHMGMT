"""Tests for the fees app: structures, assignments, payments and references."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.testing import DemoDataTestCase
from fees.models import (
    FeeItem,
    FeeStructure,
    Payment,
    SchoolBankAccount,
    StudentFeeAssignment,
    StudentPaymentReference,
)


class FeeStructureModelTests(DemoDataTestCase):
    def test_total_amount_is_sum_of_items(self):
        fee = FeeStructure.objects.get(pk=self.demo.fee_structures[0].pk)

        self.assertEqual(fee.amount, Decimal("740.00"))
        self.assertEqual(fee.items.count(), 6)

    def test_update_total_amount_recalculates(self):
        fee = self.demo.fee_structures[0]
        FeeItem.objects.create(fee_structure=fee, name="Extra", amount=Decimal("10.00"))

        fee.update_total_amount()
        fee.refresh_from_db()

        self.assertEqual(fee.amount, Decimal("750.00"))

    def test_string_includes_currency_symbol(self):
        fee = self.demo.fee_structures[0]
        self.assertIn("GH₵", str(fee))


class StudentFeeAssignmentTests(DemoDataTestCase):
    def setUp(self):
        self.fee = self.demo.fee_structures[0]
        self.second_student = self.demo.students[self.demo_levels[0]][1]

    def _assignment(self, student):
        return StudentFeeAssignment.objects.get(
            student=student,
            fee_structure=self.fee,
            term=self.current_term,
        )

    def test_fully_paid_assignment_has_zero_balance(self):
        assignment = self._assignment(self.student)

        self.assertEqual(assignment.amount, Decimal("740.00"))
        self.assertEqual(assignment.amount_paid, Decimal("740.00"))
        self.assertEqual(assignment.balance, Decimal("0.00"))

    def test_partially_paid_assignment_reports_remaining_balance(self):
        assignment = self._assignment(self.second_student)

        self.assertEqual(assignment.amount_paid, Decimal("370.00"))
        self.assertEqual(assignment.balance, Decimal("370.00"))

    def test_pending_payments_are_not_counted_as_paid(self):
        assignment = self._assignment(self.second_student)
        Payment.objects.create(
            school=self.school,
            student=self.second_student,
            assignment=assignment,
            amount=Decimal("100.00"),
            payment_method="PAYSTACK",
            status="PENDING",
            gateway_type="PAYSTACK",
            paystack_reference="PS-PENDING-BALANCE",
            receipt_number="RCPT-PENDING-BALANCE",
            payment_date=date.today(),
        )

        self.assertTrue(assignment.payments.filter(status="PENDING").exists())
        self.assertEqual(assignment.amount_paid, Decimal("370.00"))
        self.assertEqual(assignment.balance, Decimal("370.00"))


class SchoolBankAccountTests(DemoDataTestCase):
    def test_setting_a_new_default_unsets_the_previous_one(self):
        original = SchoolBankAccount.objects.get(
            school=self.school, account_type="BANK", is_default=True
        )

        replacement = SchoolBankAccount.objects.create(
            school=self.school,
            account_type="BANK",
            bank_name="Ecobank",
            account_name="Greenwood",
            account_number="999999",
            is_default=True,
        )

        original.refresh_from_db()
        self.assertFalse(original.is_default)
        self.assertTrue(replacement.is_default)

    def test_display_info_for_bank_and_mobile_money(self):
        bank = SchoolBankAccount.objects.get(school=self.school, account_type="BANK")
        mobile = SchoolBankAccount.objects.get(
            school=self.school, account_type="MOBILE_MONEY"
        )

        self.assertEqual(bank.get_display_info()["type"], "Bank Account")
        self.assertEqual(mobile.get_display_info()["type"], "Mobile Money")
        self.assertIn("MTN", mobile.get_display_info()["network"])


class StudentPaymentReferenceTests(DemoDataTestCase):
    def test_reference_is_generated_with_school_prefix(self):
        reference = StudentPaymentReference.objects.get(student=self.student)

        self.assertTrue(reference.reference_code.startswith("GREEN-STU-"))
        self.assertEqual(len(reference.reference_code.split("-")), 3)


class FeesViewTests(DemoDataTestCase):
    def test_admin_and_student_dashboards_render(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.student_user)
        response = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_teacher_is_redirected_away_from_payment_dashboard(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_fee_list_requires_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("fees:fee_list")).status_code, 200)

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("fees:fee_list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def _pending_payment(self, reference):
        assignment = StudentFeeAssignment.objects.get(
            student=self.student,
            fee_structure=self.demo.fee_structures[0],
            term=self.current_term,
        )
        return Payment.objects.create(
            school=self.school,
            student=self.student,
            assignment=assignment,
            amount=Decimal("25.00"),
            payment_method="PAYSTACK",
            status="PENDING",
            gateway_type="PAYSTACK",
            paystack_reference=reference,
            receipt_number=f"RCPT-{reference}",
            payment_date=date.today(),
        )

    def test_verifying_a_pending_payment(self):
        payment = self._pending_payment("PS-VERIFY-ME")
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("fees:verify_payment", args=[payment.pk]),
            {"action": "verify"},
        )

        self.assertRedirects(response, reverse("fees:dashboard"))
        payment.refresh_from_db()
        self.assertEqual(payment.status, "VERIFIED")
        self.assertIsNotNone(payment.verified_at)

    def test_rejecting_a_pending_payment_marks_it_failed(self):
        payment = self._pending_payment("PS-REJECT-ME")
        self.client.force_login(self.admin)

        self.client.post(
            reverse("fees:verify_payment", args=[payment.pk]),
            {"action": "reject"},
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, "FAILED")

    def test_student_search_api_returns_balances_and_references(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("fees:student_search_api"), {"q": self.student_user.first_name}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload["students"]), 1)
        self.assertEqual(payload["students"][0]["name"], self.student_user.get_full_name)
        self.assertTrue(payload["students"][0]["payment_reference"].startswith("GREEN-STU-"))

    def test_defaulters_list_renders_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("fees:defaulters_list"))
        self.assertEqual(response.status_code, 200)
