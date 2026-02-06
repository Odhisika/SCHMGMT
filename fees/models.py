from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import uuid

from accounts.models import Student
from core.models import Term


class FeeStructure(models.Model):
    """School fee categories and pricing"""
    school = models.ForeignKey('school.School', on_delete=models.CASCADE, related_name='fee_structures')
    name = models.CharField(max_length=100, help_text=_("e.g., Tuition Fee, Exam Fee"))
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text=_("Total calculated amount"))
    level = models.CharField(
        max_length=25, 
        choices=settings.LEVEL_CHOICES, 
        blank=True,
        help_text=_("Leave blank for all levels")
    )
    term = models.CharField(
        max_length=20,
        choices=settings.TERM_CHOICES,
        blank=True,
        help_text=_("Leave blank for all terms")
    )
    is_active = models.BooleanField(default=True)
    auto_assign = models.BooleanField(
        default=True,
        help_text=_("Automatically assign this fee to all students in the specified level/term")
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Fee Structure")
        verbose_name_plural = _("Fee Structures")
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.school.name} - {settings.CURRENCY}{self.amount}"

    def update_total_amount(self):
        """Recalculate total amount from items"""
        total = self.items.aggregate(models.Sum('amount'))['amount__sum'] or 0
        self.amount = total
        self.save()


class FeeItem(models.Model):
    """Individual breakdown items for a fee structure (e.g., Tuition, PTA, Sports)"""
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"{self.name} ({self.amount})"


class StudentFeeAssignment(models.Model):
    """Fees assigned to a specific student for a term"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fee_assignments')
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text=_("Can override default fee amount")
    )
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['student', 'fee_structure', 'term']
        verbose_name = _("Student Fee Assignment")
        verbose_name_plural = _("Student Fee Assignments")
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.student} - {self.fee_structure.name} - {self.term}"
    
    @property
    def amount_paid(self):
        """Total amount paid for this assignment"""
        from django.db.models import Sum
        total = self.payments.filter(status='VERIFIED').aggregate(Sum('amount'))['amount__sum']
        return total or Decimal('0.00')
    
    @property
    def balance(self):
        """Outstanding balance"""
        return self.amount - self.amount_paid


class Payment(models.Model):
    """Payment record (online or manual)"""
    PAYMENT_METHOD_CHOICES = [
        ('PAYSTACK', _('Paystack (Online)')),
        ('CASH', _('Cash')),
        ('BANK_TRANSFER', _('Bank Transfer')),
        ('CHEQUE', _('Cheque')),
        ('MOBILE_MONEY', _('Mobile Money')),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', _('Pending Verification')),
        ('VERIFIED', _('Verified')),
        ('FAILED', _('Failed')),
        ('REFUNDED', _('Refunded')),
    ]
    
    school = models.ForeignKey('school.School', on_delete=models.CASCADE, related_name='payments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')
    assignment = models.ForeignKey(
        StudentFeeAssignment, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        help_text=_("Link to specific fee assignment")
    )
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    gateway_type = models.CharField(
        max_length=20,
        default='MANUAL',
        help_text=_("Payment gateway used (MANUAL, HUBTEL, etc.)")
    )
    
    # Paystack fields
    paystack_reference = models.CharField(max_length=100, blank=True, unique=True, null=True)
    paystack_data = models.JSONField(blank=True, null=True, help_text=_("Raw Paystack response"))
    
    # Manual payment fields
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_payments'
    )
    receipt_number = models.CharField(max_length=50, blank=True)
    payment_date = models.DateField()
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['school', 'status', 'payment_date']),
        ]
    
    def __str__(self):
        return f"{self.student} - {settings.CURRENCY}{self.amount} - {self.get_status_display()}"


class SchoolBankAccount(models.Model):
    """Bank account or mobile money details for payment collection"""
    ACCOUNT_TYPE_CHOICES = [
        ('BANK', _('Bank Account')),
        ('MOBILE_MONEY', _('Mobile Money')),
    ]
    
    MOBILE_NETWORK_CHOICES = [
        ('MTN', _('MTN Mobile Money')),
        ('VODAFONE', _('Vodafone Cash')),
        ('AIRTELTIGO', _('AirtelTigo Money')),
    ]
    
    school = models.ForeignKey('school.School', on_delete=models.CASCADE, related_name='bank_accounts')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='BANK')
    
    # Bank account fields
    bank_name = models.CharField(max_length=100, blank=True, help_text=_("e.g., GCB Bank, Ecobank"))
    account_name = models.CharField(max_length=150, help_text=_("Account holder name"))
    account_number = models.CharField(max_length=50, blank=True, help_text=_("Bank account number"))
    branch = models.CharField(max_length=100, blank=True, help_text=_("Bank branch name"))
    swift_code = models.CharField(max_length=20, blank=True, help_text=_("For international transfers"))
    
    # Mobile Money fields
    mobile_money_number = models.CharField(max_length=20, blank=True, help_text=_("Mobile Money number"))
    mobile_money_network = models.CharField(max_length=20, choices=MOBILE_NETWORK_CHOICES, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text=_("Primary account displayed to students")
    )
    
    notes = models.TextField(blank=True, help_text=_("Additional instructions for students"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("School Bank Account")
        verbose_name_plural = _("School Bank Accounts")
        ordering = ['-is_default', '-is_active', 'account_type']
    
    def __str__(self):
        if self.account_type == 'BANK':
            return f"{self.bank_name} - {self.account_number}"
        else:
            return f"{self.get_mobile_money_network_display()} - {self.mobile_money_number}"
    
    def get_display_info(self):
        """Return formatted account details for display"""
        if self.account_type == 'BANK':
            return {
                'type': 'Bank Account',
                'bank': self.bank_name,
                'account_name': self.account_name,
                'account_number': self.account_number,
                'branch': self.branch,
            }
        else:
            return {
                'type': 'Mobile Money',
                'network': self.get_mobile_money_network_display(),
                'number': self.mobile_money_number,
                'name': self.account_name,
            }
    
    def save(self, *args, **kwargs):
        # Ensure only one default account per type per school
        if self.is_default:
            SchoolBankAccount.objects.filter(
                school=self.school,
                account_type=self.account_type,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class StudentPaymentReference(models.Model):
    """Unique payment reference for each student"""
    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name='payment_reference'
    )
    reference_code = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        help_text=_("Unique payment reference code")
    )
    qr_code = models.ImageField(
        upload_to='payment_qr_codes/',
        blank=True,
        null=True,
        help_text=_("QR code for payment reference")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _("Student Payment Reference")
        verbose_name_plural = _("Student Payment References")
    
    def __str__(self):
        return f"{self.student} - {self.reference_code}"
    
    def save(self, *args, **kwargs):
        if not self.reference_code:
            # Generate unique reference: SCH-{school_slug}-STU-{uuid}
            school_code = self.student.student.school.slug.upper()[:5] if self.student.student.school else 'SCH'
            unique_id = str(uuid.uuid4())[:8].upper()
            self.reference_code = f"{school_code}-STU-{unique_id}"
            
            # Ensure uniqueness
            while StudentPaymentReference.objects.filter(reference_code=self.reference_code).exists():
                unique_id = str(uuid.uuid4())[:8].upper()
                self.reference_code = f"{school_code}-STU-{unique_id}"
        
        super().save(*args, **kwargs)
