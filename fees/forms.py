from django import forms
from django.forms import inlineformset_factory
from .models import FeeStructure, StudentFeeAssignment, Payment, FeeItem, SchoolBankAccount
from accounts.models import Student


class ManualPaymentForm(forms.ModelForm):
    """Form for recording manual payments"""
    
    class Meta:
        model = Payment
        fields = ['student', 'assignment', 'amount', 'payment_method', 'payment_date', 'receipt_number', 'notes']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'receipt_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, school=None, initial_student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school
        
        if school:
            self.fields['student'].queryset = Student.objects.filter(student__school=school)
            
        if initial_student:
            self.fields['student'].initial = initial_student
            self.fields['student'].widget = forms.HiddenInput()
            
            # Filter assignments for this student
            self.fields['assignment'].queryset = StudentFeeAssignment.objects.filter(
                student=initial_student
            )
        
        # Add CSS classes
        for field in self.fields:
            if field not in ['student']:
                self.fields[field].widget.attrs['class'] = 'form-control'
    
    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        assignment = cleaned_data.get('assignment')
        
        if amount and assignment:
            # Check for overpayment
            if amount > assignment.balance:
                from django.utils.translation import gettext as _
                self.add_error('amount', _(f"Amount exceeds outstanding balance of {assignment.balance}"))
        
        return cleaned_data


class FeeStructureForm(forms.ModelForm):
    """Form for creating/editing fee structures"""
    
    class Meta:
        model = FeeStructure
        fields = ['name', 'level', 'term', 'auto_assign', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Fee Name (e.g. Term 1 Fees)'}),
            'level': forms.Select(attrs={'class': 'form-select'}),
            'term': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


FeeItemFormSet = inlineformset_factory(
    FeeStructure,
    FeeItem,
    fields=('name', 'amount'),
    extra=1,
    can_delete=True,
    widgets={
        'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item Name (e.g. Tuition)'}),
        'amount': forms.NumberInput(attrs={'class': 'form-control item-amount', 'step': '0.01', 'placeholder': '0.00'}),
    }
)


class FeeReplicationForm(forms.Form):
    """Form to select grade levels for fee replication"""
    target_levels = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Select Classes to Replicate To",
        required=True
    )

    def __init__(self, *args, current_level=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.conf import settings
        
        # Populate choices from settings.LEVEL_CHOICES
        # Exclude the current level to avoid duplicating to self
        choices = []
        if hasattr(settings, 'LEVEL_CHOICES'):
            for value, label in settings.LEVEL_CHOICES:
                if value != current_level:
                    choices.append((value, label))
        
        self.fields['target_levels'].choices = choices


class SchoolBankAccountForm(forms.ModelForm):
    """Form for managing school bank accounts and mobile money details"""
    
    class Meta:
        model = SchoolBankAccount
        fields = [
            'account_type', 'bank_name', 'account_name', 'account_number',
            'branch', 'swift_code', 'mobile_money_number', 'mobile_money_network',
            'is_active', 'is_default', 'notes'
        ]
        widgets = {
            'account_type': forms.Select(attrs={'class': 'form-select', 'id': 'account-type-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control bank-field', 'placeholder': 'e.g., GCB Bank, Ecobank'}),
            'account_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account holder name'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control bank-field', 'placeholder': 'Account number'}),
            'branch': forms.TextInput(attrs={'class': 'form-control bank-field', 'placeholder': 'Branch name'}),
            'swift_code': forms.TextInput(attrs={'class': 'form-control bank-field', 'placeholder': 'SWIFT/BIC code (optional)'}),
            'mobile_money_number': forms.TextInput(attrs={'class': 'form-control momo-field', 'placeholder': 'e.g., 0244123456'}),
            'mobile_money_network': forms.Select(attrs={'class': 'form-select momo-field'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Additional payment instructions (optional)'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        account_type = cleaned_data.get('account_type')
        
        if account_type == 'BANK':
            # Validate bank fields are filled
            if not cleaned_data.get('bank_name'):
                self.add_error('bank_name', 'Bank name is required for bank accounts')
            if not cleaned_data.get('account_number'):
                self.add_error('account_number', 'Account number is required for bank accounts')
        else:
            # Validate mobile money fields are filled
            if not cleaned_data.get('mobile_money_number'):
                self.add_error('mobile_money_number', 'Mobile money number is required')
            if not cleaned_data.get('mobile_money_network'):
                self.add_error('mobile_money_network', 'Network is required for mobile money')
        
        return cleaned_data
