from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.db.models import Sum
from django.http import Http404
from datetime import date
from decimal import Decimal

from accounts.decorators import admin_required, student_required
from accounts.models import Student
from core.models import Term
from .models import FeeStructure, StudentFeeAssignment, Payment, SchoolBankAccount, StudentPaymentReference


@login_required
def payment_dashboard(request):
    """Main payment dashboard - role-based view"""
    if request.user.is_superuser or request.user.is_school_admin:
        return admin_payment_dashboard(request)
    elif request.user.is_student:
        return student_payment_dashboard(request)
    else:
        messages.error(request, _("You don't have access to the payment system."))
        return redirect('home')


def admin_payment_dashboard(request):
    """Admin payment overview"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    
    # Get current division and level from request
    current_division = request.GET.get('division', 'all')
    selected_level = request.GET.get('level')
    
    # Division levels for filtering
    if current_division == 'all':
        division_levels = [] # No specific division levels to restrict to
        current_division_display = _("All Divisions")
    else:
        division_levels = settings.DIVISION_LEVEL_MAPPING.get(current_division, [])
        current_division_display = dict([
            (settings.DIVISION_NURSERY, _("Nursery/Pre-School")),
            (settings.DIVISION_PRIMARY, _("Primary School")),
            (settings.DIVISION_JHS, _("Junior High School")),
        ]).get(current_division, current_division)

    # Base querysets
    payments_qs = Payment.objects.filter(school=request.school)
    assignments_qs = StudentFeeAssignment.objects.filter(student__student__school=request.school)
    
    # Apply filtering
    if current_division != 'all' and division_levels:
        payments_qs = payments_qs.filter(student__level__in=division_levels)
        assignments_qs = assignments_qs.filter(student__level__in=division_levels)
        
    if selected_level:
        payments_qs = payments_qs.filter(student__level=selected_level)
        assignments_qs = assignments_qs.filter(student__level=selected_level)

    # Recent payments (filtered)
    recent_payments = payments_qs.select_related('student', 'assignment').order_by('-created_at')[:20]
    
    # Pending payments (filtered)
    pending_payments = payments_qs.filter(status='PENDING').select_related('student').order_by('-created_at')
    
    # Statistics (filtered)
    total_collected = payments_qs.filter(status='VERIFIED').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_pending = payments_qs.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    # Calculate collection rate percentage
    total_expected = assignments_qs.aggregate(Sum('fee_structure__amount'))['fee_structure__amount__sum'] or Decimal('1.00')
    collection_rate = round((total_collected / total_expected) * 100, 1) if total_expected > 0 else 0

    # Fee Structure Breakdown (filtered by division/level if relevant, or just active ones)
    fee_structures = FeeStructure.objects.filter(school=request.school, is_active=True)
    fee_breakdown = []
    
    for structure in fee_structures:
        # Calculate collected amount for this specific fee structure within filter
        collected = payments_qs.filter(
            assignment__fee_structure=structure,
            status='VERIFIED'
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        fee_breakdown.append({
            'name': structure.name,
            'amount': collected,
            'icon': 'fa-money-bill-alt'
        })
    
    # Get active bank accounts
    bank_accounts = SchoolBankAccount.objects.filter(
        school=request.school,
        is_active=True
    ).order_by('-is_default')
    
    # Prepare division level choices
    division_level_choices = []
    for code, name in settings.LEVEL_CHOICES:
        if code in division_levels:
            division_level_choices.append((code, name))

    context = {
        'title': _('Payment Management'),
        'recent_payments': recent_payments,
        'pending_payments': pending_payments,
        'total_collected': total_collected,
        'total_pending': total_pending,
        'collection_rate': collection_rate,
        'fee_breakdown': fee_breakdown,
        'current_term': current_term,
        'bank_accounts': bank_accounts,
        'current_division': current_division,
        'current_division_name': current_division_display,
        'selected_level': selected_level,
        'division_levels': division_level_choices,
        'divisions': [
            ('all', _("All Divisions")),
            (settings.DIVISION_NURSERY, _("Nursery/Pre-School")),
            (settings.DIVISION_PRIMARY, _("Primary School")),
            (settings.DIVISION_JHS, _("Junior High School")),
        ],
    }
    return render(request, 'fees/admin_dashboard.html', context)


def student_payment_dashboard(request):
    """Student payment overview"""
    student = get_object_or_404(Student, student__pk=request.user.id, student__school=request.school)
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    
    # Fee assignments for current term
    assignments = StudentFeeAssignment.objects.filter(
        student=student,
        term=current_term
    ).select_related('fee_structure') if current_term else []
    
    # Payment history
    payments = Payment.objects.filter(
        student=student
    ).select_related('assignment').order_by('-created_at')[:20]
    
    # Calculate total balance
    total_balance = sum(a.balance for a in assignments)
    
    # Get payment reference
    payment_reference = ''
    try:
        payment_reference = student.payment_reference.reference_code
    except:
        pass
    
    # Get active bank accounts for display
    bank_accounts = SchoolBankAccount.objects.filter(
        school=request.school,
        is_active=True
    ).order_by('-is_default')
    
    context = {
        'title': _('My Payments'),
        'student': student,
        'assignments': assignments,
        'payments': payments,
        'total_balance': total_balance,
        'current_term': current_term,
        'payment_reference': payment_reference,
        'bank_accounts': bank_accounts,
    }
    return render(request, 'fees/student_dashboard.html', context)


@login_required
@admin_required
def fee_structure_list(request):
    """Manage fee structures"""
    fees = FeeStructure.objects.filter(school=request.school).order_by('-created_at')
    
    context = {
        'title': _('Fee Structure Management'),
        'fees': fees,
    }
    return render(request, 'fees/fee_list.html', context)


@login_required
@admin_required
def fee_structure_create(request):
    """Create a new fee structure"""
    from .forms import FeeStructureForm, FeeItemFormSet
    
    if request.method == 'POST':
        form = FeeStructureForm(request.POST)
        formset = FeeItemFormSet(request.POST, prefix='items')
        
        if form.is_valid() and formset.is_valid():
            fee = form.save(commit=False)
            fee.school = request.school
            fee.save()
            
            items = formset.save(commit=False)
            for item in items:
                item.fee_structure = fee
                item.save()
            
            # Update total amount
            fee.update_total_amount()
            
            messages.success(request, _("Fee structure created successfully!"))
            return redirect('fees:fee_list')
    else:
        form = FeeStructureForm()
        formset = FeeItemFormSet(prefix='items')
    
    context = {
        'title': _('Create Fee Structure'),
        'form': form,
        'formset': formset,
    }
    return render(request, 'fees/fee_form.html', context)


@login_required
@admin_required
def fee_structure_edit(request, pk):
    """Edit an existing fee structure"""
    from .forms import FeeStructureForm, FeeItemFormSet
    
    fee = get_object_or_404(FeeStructure, pk=pk, school=request.school)
    
    if request.method == 'POST':
        form = FeeStructureForm(request.POST, instance=fee)
        formset = FeeItemFormSet(request.POST, instance=fee, prefix='items')
        
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            
            # Update total amount
            fee.update_total_amount()
            
            messages.success(request, _("Fee structure updated successfully!"))
            return redirect('fees:fee_list')
    else:
        form = FeeStructureForm(instance=fee)
        formset = FeeItemFormSet(instance=fee, prefix='items')
    
    context = {
        'title': _('Edit Fee Structure'),
        'form': form,
        'fee': fee,
        'formset': formset,
    }
    return render(request, 'fees/fee_form.html', context)


@login_required
@admin_required
def fee_structure_delete(request, pk):
    """Delete a fee structure"""
    fee = get_object_or_404(FeeStructure, pk=pk, school=request.school)
    
    if request.method == 'POST':
        fee.delete()
        messages.success(request, _("Fee structure deleted successfully!"))
        return redirect('fees:fee_list')
    
    context = {
        'title': _('Delete Fee Structure'),
        'fee': fee,
    }
    return render(request, 'fees/fee_confirm_delete.html', context)


@login_required
@admin_required
def duplicate_fee_structure(request, pk):
    """Duplicate a fee structure to specific grade levels"""
    source_fee = get_object_or_404(FeeStructure, pk=pk, school=request.school)
    
    from .forms import FeeReplicationForm
    
    if request.method == 'POST':
        form = FeeReplicationForm(request.POST, current_level=source_fee.level)
        
        if form.is_valid():
            target_levels = form.cleaned_data['target_levels']
            
            from .models import FeeItem
            from django.db import transaction
            
            created_count = 0
            
            try:
                with transaction.atomic():
                    for level in target_levels:
                        # Check if similar fee already exists
                        if not FeeStructure.objects.filter(
                            school=request.school,
                            name=source_fee.name,
                            term=source_fee.term,
                            level=level
                        ).exists():
                            # Clone parent
                            new_fee = FeeStructure.objects.create(
                                school=request.school,
                                name=source_fee.name,
                                amount=source_fee.amount,
                                level=level,
                                term=source_fee.term,
                                is_active=source_fee.is_active,
                                description=source_fee.description
                            )
                            
                            # Clone items
                            for item in source_fee.items.all():
                                FeeItem.objects.create(
                                    fee_structure=new_fee,
                                    name=item.name,
                                    amount=item.amount
                                )
                            
                            created_count += 1
                    
                    if created_count > 0:
                        messages.success(request, _(f"Fee structure replicated to {created_count} classes successfully!"))
                    else:
                        messages.warning(request, _("No new fee structures created. They may already exist for selected classes."))
                        
                    return redirect('fees:fee_list')
            
            except Exception as e:
                messages.error(request, _(f"An error occurred during replication: {str(e)}"))
                
    else:
        form = FeeReplicationForm(current_level=source_fee.level)
    
    context = {
        'title': _('Replicate Fee Structure'),
        'form': form,
        'source_fee': source_fee,
    }
    return render(request, 'fees/fee_replication_form.html', context)


@login_required
@admin_required
@login_required
@admin_required
def record_manual_payment(request, student_id=None):
    """Admin records a manual payment"""
    from .forms import ManualPaymentForm
    from django.utils import timezone
    from django.db.models import Sum
    
    student = None
    if student_id:
        student = get_object_or_404(Student, pk=student_id, student__school=request.school)
    
    if request.method == 'POST':
        # Convert student_id from hidden field if present and not in URL
        post_student_id = request.POST.get('student')
        if not student and post_student_id:
             student = get_object_or_404(Student, pk=post_student_id, student__school=request.school)

        form = ManualPaymentForm(request.POST, school=request.school, initial_student=student)
        
        # We need to manually validate the amount against total balance here because 
        # the form doesn't know about all assignments, just the specific 'assignment' field which might be empty
        if form.is_valid():
            amount = form.cleaned_data['amount']
            
            # Find current term assignments
            current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
            if not current_term:
                messages.error(request, _("No active term found to record payment against."))
                return redirect('fees:record_payment')

            assignments = StudentFeeAssignment.objects.filter(student=student, term=current_term)
            total_balance = sum(a.balance for a in assignments)
            
            if amount > total_balance:
                 messages.error(request, _(f"Payment amount (GH₵{amount}) exceeds total outstanding balance (GH₵{total_balance})."))
                 # Re-render with error
                 context = {
                    'title': _('Record Manual Payment'),
                    'form': form,
                    'student': student,
                    'level_choices': settings.LEVEL_CHOICES,
                 }
                 return render(request, 'fees/record_payment.html', context)

            # Auto-allocate payment to assignments
            # Simple strategy: Pay off assignments in order (or just the first one found)
            # Since we can only link to ONE assignment per Payment model design, 
            # we will link to the one with the largest debt or the first one.
            # ideally we should split payments, but for now we link to the primary assignment.
            
            target_assignment = None
            for assignment in assignments:
                if assignment.balance > 0:
                    target_assignment = assignment
                    break # Just take the first one with debt
            
            payment = form.save(commit=False)
            payment.school = request.school
            payment.recorded_by = request.user
            payment.payment_method = form.cleaned_data['payment_method']
            
            if target_assignment:
                payment.assignment = target_assignment
            
            # Manual payments recorded by admin are automatically verified
            payment.status = 'VERIFIED'
            payment.gateway_type = 'MANUAL'
            payment.verified_at = timezone.now()
            
            payment.save()
                
            messages.success(request, _(f"Payment of GH₵{payment.amount} recorded and verified successfully!"))
            
            # Redirect back to record payment page (clears form)
            return redirect('fees:record_payment')
    else:
        form = ManualPaymentForm(school=request.school, initial_student=student)
    
    context = {
        'title': _('Record Manual Payment'),
        'form': form,
        'student': student,
        'level_choices': settings.LEVEL_CHOICES,
    }
    return render(request, 'fees/record_payment.html', context)


@login_required
@admin_required
def verify_payment(request, payment_id):
    """Admin verifies a pending payment"""
    payment = get_object_or_404(Payment, pk=payment_id, school=request.school)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'verify':
            payment.status = 'VERIFIED'
            from django.utils import timezone
            payment.verified_at = timezone.now()
            payment.save()
            messages.success(request, _("Payment verified successfully!"))
        elif action == 'reject':
            payment.status = 'FAILED'
            payment.save()
            messages.info(request, _("Payment marked as failed."))
        
        return redirect('fees:admin_dashboard')
    
    context = {
        'title': _('Verify Payment'),
        'payment': payment,
    }
    return render(request, 'fees/verify_payment.html', context)


@login_required
@admin_required
def payment_edit(request, pk):
    """Edit an existing payment record"""
    from .forms import ManualPaymentForm
    
    payment = get_object_or_404(Payment, pk=pk, school=request.school)
    student = payment.student
    
    if request.method == 'POST':
        form = ManualPaymentForm(request.POST, instance=payment, school=request.school, initial_student=student)
        if form.is_valid():
            form.save()
            messages.success(request, _("Payment record updated successfully!"))
            return redirect('fees:dashboard')
    else:
        form = ManualPaymentForm(instance=payment, school=request.school, initial_student=student)
    
    context = {
        'title': _('Edit Payment'),
        'form': form,
        'payment': payment,
        'student': student,
    }
    return render(request, 'fees/payment_edit.html', context)


@login_required
@admin_required
def payment_delete(request, pk):
    """Delete a payment record"""
    payment = get_object_or_404(Payment, pk=pk, school=request.school)
    
    if request.method == 'POST':
        payment.delete()
        messages.success(request, _("Payment record deleted successfully!"))
        return redirect('fees:dashboard')
    
    context = {
        'title': _('Delete Payment'),
        'payment': payment,
    }
    return render(request, 'fees/payment_confirm_delete.html', context)


@login_required
def payment_history(request, student_id=None):
    """View payment history"""
    if request.user.is_student:
        student = get_object_or_404(Student, student__pk=request.user.id, student__school=request.school)
    elif student_id and (request.user.is_superuser or request.user.is_school_admin):
        student = get_object_or_404(Student, pk=student_id, student__school=request.school)
    else:
        raise Http404
    
    payments = Payment.objects.filter(
        student=student,
        school=request.school
    ).select_related('assignment', 'recorded_by').order_by('-created_at')
    
    context = {
        'title': _('Payment History'),
        'student': student,
        'payments': payments,
    }
    return render(request, 'fees/payment_history.html', context)


# Paystack integration views will be added in next phase
@login_required
@student_required
def initiate_paystack_payment(request, assignment_id):
    """Initiate Paystack payment for a fee assignment"""
    student = get_object_or_404(Student, student__pk=request.user.id, student__school=request.school)
    assignment = get_object_or_404(StudentFeeAssignment, pk=assignment_id, student=student)
    
    # TODO: Implement Paystack initialization
    messages.info(request, _("Paystack integration coming soon!"))
    return redirect('fees:dashboard')


@login_required
def paystack_callback(request):
    """Handle Paystack payment callback"""
    # TODO: Implement Paystack verification
    messages.info(request, _("Payment verification in progress..."))
    return redirect('fees:dashboard')


# === Enhanced Payment System Views ===

@login_required
@admin_required
def student_search_api(request):
    """AJAX endpoint for searching students by name, ID, or class"""
    from django.http import JsonResponse
    from django.db.models import Q
    
    query = request.GET.get('q', '').strip()
    class_filter = request.GET.get('class', '').strip()
    
    if not query and not class_filter:
        return JsonResponse({'students': []})
    
    students = Student.objects.filter(student__school=request.school).select_related('student')
    
    # Apply search query
    if query:
        students = students.filter(
            Q(student__username__icontains=query) |
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__email__icontains=query) |
            Q(id__icontains=query)
        )
    
    # Apply class filter
    if class_filter:
        students = students.filter(level=class_filter)
    
    # Limit results
    students = students[:20]
    
    # Build response with payment reference
    results = []
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    
    for student in students:
        # Get payment reference
        payment_ref = ''
        try:
            payment_ref = student.payment_reference.reference_code
        except:
            pass
        
        # Calculate outstanding balance
        balance = Decimal('0.00')
        if current_term:
            assignments = StudentFeeAssignment.objects.filter(student=student, term=current_term)
            balance = sum(a.balance for a in assignments)
        
        results.append({
            'id': student.id,
            'name': student.student.get_full_name,
            'username': student.student.username,
            'level': student.level,
            'payment_reference': payment_ref,
            'outstanding_balance': float(balance),
        })
    
    return JsonResponse({'students': results})


@login_required
@admin_required
def bank_account_list(request):
    """List and manage school bank accounts"""
    from .models import SchoolBankAccount
    
    accounts = SchoolBankAccount.objects.filter(school=request.school).order_by('-is_default', '-is_active')
    
    context = {
        'title': _('Bank Account Management'),
        'accounts': accounts,
    }
    return render(request, 'fees/bank_account_list.html', context)


@login_required
@admin_required
def bank_account_create(request):
    """Create a new school bank account"""
    from .forms import SchoolBankAccountForm
    from .models import SchoolBankAccount
    
    if request.method == 'POST':
        form = SchoolBankAccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.school = request.school
            account.save()
            messages.success(request, _("Bank account added successfully!"))
            return redirect('fees:bank_account_list')
    else:
        form = SchoolBankAccountForm()
    
    context = {
        'title': _('Add Bank Account'),
        'form': form,
    }
    return render(request, 'fees/bank_account_form.html', context)


@login_required
@admin_required
def bank_account_edit(request, pk):
    """Edit an existing school bank account"""
    from .forms import SchoolBankAccountForm
    from .models import SchoolBankAccount
    
    account = get_object_or_404(SchoolBankAccount, pk=pk, school=request.school)
    
    if request.method == 'POST':
        form = SchoolBankAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, _("Bank account updated successfully!"))
            return redirect('fees:bank_account_list')
    else:
        form = SchoolBankAccountForm(instance=account)
    
    context = {
        'title': _('Edit Bank Account'),
        'form': form,
        'account': account,
    }
    return render(request, 'fees/bank_account_form.html', context)


@login_required
@admin_required
def bank_account_toggle(request, pk):
    """Toggle bank account active status"""
    from .models import SchoolBankAccount
    
    account = get_object_or_404(SchoolBankAccount, pk=pk, school=request.school)
    
    if request.method == 'POST':
        account.is_active = not account.is_active
        account.save()
        
        status = _("activated") if account.is_active else _("deactivated")
        messages.success(request, _(f"Bank account {status} successfully!"))
    
    return redirect('fees:bank_account_list')

@login_required
@admin_required
def defaulters_list(request):
    """View to see students with outstanding fees and those who have fully paid"""
    current_term = Term.objects.filter(is_current_term=True, school=request.school).first()
    
    current_division = request.GET.get('division', 'all')
    selected_level = request.GET.get('level')
    status_filter = request.GET.get('status') # 'paid', 'owing', 'partial'
    
    if current_division == 'all':
        division_levels = []
    else:
        division_levels = settings.DIVISION_LEVEL_MAPPING.get(current_division, [])
    
    # Base student queryset
    students_qs = Student.objects.filter(student__school=request.school)
    
    if current_division != 'all' and division_levels:
        students_qs = students_qs.filter(level__in=division_levels)
    
    if selected_level:
        students_qs = students_qs.filter(level=selected_level)

    student_data = []
    for student in students_qs.order_by('level', 'student__last_name'):
        # Get assignments for this term
        assignments = StudentFeeAssignment.objects.filter(student=student, term=current_term)
        
        total_fees = assignments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        total_paid = Decimal('0.00')
        
        for assignment in assignments:
            total_paid += assignment.amount_paid
            
        balance = total_fees - total_paid
        
        status = 'PAID'
        if balance > 0:
            if total_paid > 0:
                status = 'PARTIAL'
            else:
                status = 'OWING'
        
        # Apply status filter if present
        if status_filter:
            if status_filter.upper() != status:
                continue

        student_data.append({
            'student': student,
            'total_fees': total_fees,
            'total_paid': total_paid,
            'balance': balance,
            'status': status,
        })

    # Prepare context
    division_level_choices = []
    for code, name in settings.LEVEL_CHOICES:
        if code in division_levels:
            division_level_choices.append((code, name))
            
    context = {
        'title': _('Fee Defaulters & Payments'),
        'student_data': student_data,
        'current_term': current_term,
        'current_division': current_division,
        'selected_level': selected_level,
        'status_filter': status_filter,
        'division_levels': division_level_choices,
        'divisions': [
            ('all', _("All Divisions")),
            (settings.DIVISION_NURSERY, _("Nursery/Pre-School")),
            (settings.DIVISION_PRIMARY, _("Primary School")),
            (settings.DIVISION_JHS, _("Junior High School")),
        ],
    }
    return render(request, 'fees/defaulters_list.html', context)

@login_required
@admin_required
def payment_reference_lookup(request):
    """Look up student by payment reference"""
    from .models import StudentPaymentReference
    
    reference = request.GET.get('ref', '').strip()
    student = None
    
    if reference:
        try:
            payment_ref = StudentPaymentReference.objects.select_related('student__student').get(
                reference_code__iexact=reference,
                student__student__school=request.school
            )
            student = payment_ref.student
        except StudentPaymentReference.DoesNotExist:
            messages.error(request, _("No student found with that payment reference."))
    
    context = {
        'title': _('Payment Reference Lookup'),
        'student': student,
        'reference': reference,
    }
    return render(request, 'fees/payment_reference_lookup.html', context)
