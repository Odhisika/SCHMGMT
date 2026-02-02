from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from accounts.models import Student
from core.models import Term


class Invoice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    total = models.FloatField(null=True, blank=True)
    amount = models.FloatField(null=True, blank=True)
    payment_complete = models.BooleanField(default=False)
    invoice_code = models.CharField(max_length=200, blank=True, null=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)


class FeeStructure(models.Model):
    """Fee structure by grade level and term"""
    grade_level = models.CharField(max_length=20, choices=settings.LEVEL_CHOICES)
    term = models.CharField(max_length=20, choices=settings.TERM_CHOICES)
    year = models.CharField(max_length=4, help_text="Academic year (e.g., 2024)", default="2024")
    
    # Fee components (in Ghana Cedis)
    tuition_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    pta_dues = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), 
                                   help_text=_("Parent-Teacher Association dues"))
    sports_levy = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    exam_fees = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    library_fees = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    development_levy = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    other_fees = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        unique_together = ['grade_level', 'term', 'year', 'school']
        verbose_name = _("Fee Structure")
        verbose_name_plural = _("Fee Structures")
        ordering = ['year', 'term', 'grade_level']
    
    def __str__(self):
        return f"{self.grade_level} - {self.term} - {self.year}"
    
    @property
    def total_fees(self):
        """Calculate total fees"""
        return sum([
            self.tuition_fee,
            self.pta_dues,
            self.sports_levy,
            self.exam_fees,
            self.library_fees,
            self.development_levy,
            self.other_fees
        ])


CASH = "Cash"
MOBILE_MONEY = "Mobile Money"
BANK_TRANSFER = "Bank Transfer"
CHEQUE = "Cheque"

PAYMENT_METHOD_CHOICES = (
    (CASH, _("Cash")),
    (MOBILE_MONEY, _("Mobile Money (MTN, Vodafone, AirtelTigo)")),
    (BANK_TRANSFER, _("Bank Transfer")),
    (CHEQUE, _("Cheque")),
)


class StudentPayment(models.Model):
    """Track individual student fee payments"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="fee_payments")
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Payment details
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES, default=CASH)
    reference_number = models.CharField(max_length=100, blank=True, 
                                       help_text=_("Mobile Money ref or transaction ID"))
    receipt_number = models.CharField(max_length=50, unique=True)
    
    # Additional info
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, 
                                   null=True, related_name="payments_received")
    remarks = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    school = models.ForeignKey("school.School", on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        ordering = ['-payment_date', '-created_at']
        verbose_name = _("Student Payment")
        verbose_name_plural = _("Student Payments")
    
    def __str__(self):
        return f"{self.student} - GH₵{self.amount_paid} - {self.payment_date}"
    
    @property
    def total_fees_for_term(self):
        """Get total fees expected for this student's term"""
        if self.fee_structure:
            return self.fee_structure.total_fees
        return Decimal('0.00')
    
    @property
    def total_paid_for_term(self):
        """Calculate total amount paid by student for this term"""
        payments = StudentPayment.objects.filter(
            student=self.student,
            term=self.term,
            session=self.session
        )
        return sum(payment.amount_paid for payment in payments)
    
    @property
    def balance_owed(self):
        """Calculate outstanding balance"""
        return self.total_fees_for_term - self.total_paid_for_term

