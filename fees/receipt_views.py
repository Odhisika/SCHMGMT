"""
Additional views for PDF receipt download
"""
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Payment
from .receipts import PaymentReceiptGenerator


@login_required
def download_payment_receipt(request, payment_id):
    """Generate and download PDF receipt for a payment"""
    user = request.user
    school = request.school or getattr(user, "school", None)

    # Get payment - students can only download their own receipts
    if user.is_superuser:
        # Superusers can download any receipt
        payment = get_object_or_404(Payment, pk=payment_id)
    elif user.is_school_admin:
        # School admins can download any receipt for their school
        payment = get_object_or_404(Payment, pk=payment_id, school=school)
    elif user.is_student:
        # Students can only download their own receipts
        payment = get_object_or_404(
            Payment,
            pk=payment_id,
            student__student=user,
            school=school
        )
    else:
        raise PermissionDenied(
            "You do not have permission to download this receipt."
        )

    # Students may only download verified receipts. Admins can also download
    # pending payments as internal records (the receipt prints its status).
    is_admin = user.is_superuser or user.is_school_admin
    if payment.status != 'VERIFIED' and not is_admin:
        return HttpResponse("Receipt not available - payment not yet verified", status=403)
    
    # Generate PDF
    generator = PaymentReceiptGenerator(payment)
    pdf_buffer = generator.generate()
    
    # Create response
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{payment.id}_{payment.payment_date}.pdf"'
    
    return response
