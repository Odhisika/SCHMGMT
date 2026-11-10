"""Tests for the legacy payments app models."""

from datetime import date
from decimal import Decimal

from core.testing import DemoDataTestCase
from payments.models import FeeStructure as PaymentFeeStructure
from payments.models import Invoice, StudentPayment


class PaymentFeeStructureTests(DemoDataTestCase):
    def test_total_fees_sums_all_components(self):
        fee = PaymentFeeStructure.objects.create(
            grade_level="Primary 1",
            term=self.current_term.term,
            year="2025",
            tuition_fee=Decimal("400.00"),
            pta_dues=Decimal("30.00"),
            sports_levy=Decimal("20.00"),
            exam_fees=Decimal("25.00"),
            library_fees=Decimal("10.00"),
            development_levy=Decimal("15.00"),
            other_fees=Decimal("5.00"),
            school=self.school,
        )

        self.assertEqual(fee.total_fees, Decimal("505.00"))
        self.assertIn("Primary 1", str(fee))


class StudentPaymentTests(DemoDataTestCase):
    def setUp(self):
        # Use a student without the seeded legacy payment so the totals below
        # only reflect the payments created by this test.
        self.student = self.demo.students[self.demo_levels[0]][1]
        self.fee = PaymentFeeStructure.objects.create(
            grade_level=self.student.level,
            term=self.current_term.term,
            year="2025",
            tuition_fee=Decimal("200.00"),
            pta_dues=Decimal("50.00"),
            sports_levy=Decimal("50.00"),
            school=self.school,
        )
        self.first_payment = StudentPayment.objects.create(
            student=self.student,
            term=self.current_term,
            fee_structure=self.fee,
            amount_paid=Decimal("120.00"),
            payment_date=date.today(),
            payment_method="Cash",
            receipt_number="LEGACY-001",
            school=self.school,
        )
        self.second_payment = StudentPayment.objects.create(
            student=self.student,
            term=self.current_term,
            fee_structure=self.fee,
            amount_paid=Decimal("80.00"),
            payment_date=date.today(),
            payment_method="Bank Transfer",
            receipt_number="LEGACY-002",
            school=self.school,
        )

    def test_total_fees_for_term_comes_from_structure(self):
        self.assertEqual(self.first_payment.total_fees_for_term, Decimal("300.00"))

    def test_total_paid_for_term_sums_all_student_payments(self):
        self.assertEqual(
            self.first_payment.total_paid_for_term, Decimal("200.00")
        )
        self.assertEqual(
            self.second_payment.total_paid_for_term, Decimal("200.00")
        )

    def test_balance_owed_uses_paid_total(self):
        self.assertEqual(self.first_payment.balance_owed, Decimal("100.00"))

    def test_payment_string_contains_amount_and_date(self):
        rendered = str(self.first_payment)
        self.assertIn("120.00", rendered)
        self.assertIn(str(date.today()), rendered)


class InvoiceTests(DemoDataTestCase):
    def test_invoice_defaults_to_incomplete(self):
        invoice = Invoice.objects.create(
            user=self.student_user,
            total=500.0,
            amount=500.0,
            invoice_code="INV-TEST-1",
            school=self.school,
        )

        self.assertFalse(invoice.payment_complete)
        self.assertEqual(invoice.school, self.school)
