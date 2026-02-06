from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import FeeStructure, FeeItem, StudentFeeAssignment, Payment, SchoolBankAccount, StudentPaymentReference


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'school', 'level', 'term', 'amount', 'auto_assign', 'is_active', 'created_at']
    list_filter = ['school', 'level', 'term', 'is_active', 'auto_assign']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']


@admin.register(StudentFeeAssignment)
class StudentFeeAssignmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'fee_structure', 'term', 'amount', 'amount_paid', 'balance', 'created_at']
    list_filter = ['term', 'fee_structure__school']
    search_fields = ['student__student__username', 'student__student__first_name', 'student__student__last_name']
    readonly_fields = ['amount_paid', 'balance', 'created_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['student', 'amount', 'payment_method', 'gateway_type', 'status', 'payment_date', 'recorded_by']
    list_filter = ['status', 'payment_method', 'gateway_type', 'school']
    search_fields = ['student__student__username', 'receipt_number', 'paystack_reference']
    readonly_fields = ['created_at', 'verified_at', 'paystack_data']
    date_hierarchy = 'payment_date'


@admin.register(SchoolBankAccount)
class SchoolBankAccountAdmin(admin.ModelAdmin):
    list_display = ['school', 'account_type', 'account_name', 'get_account_identifier', 'is_default', 'is_active']
    list_filter = ['school', 'account_type', 'is_active', 'is_default']
    search_fields = ['account_name', 'bank_name', 'account_number', 'mobile_money_number']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_account_identifier(self, obj):
        if obj.account_type == 'BANK':
            return f"{obj.bank_name} - {obj.account_number}"
        return f"{obj.get_mobile_money_network_display()} - {obj.mobile_money_number}"
    get_account_identifier.short_description = _('Account Details')


@admin.register(StudentPaymentReference)
class StudentPaymentReferenceAdmin(admin.ModelAdmin):
    list_display = ['student', 'reference_code', 'created_at']
    search_fields = ['student__student__username', 'student__student__first_name', 'student__student__last_name', 'reference_code']
    readonly_fields = ['reference_code', 'created_at']


@admin.register(FeeItem)
class FeeItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'fee_structure', 'amount']
    search_fields = ['name', 'fee_structure__name']
