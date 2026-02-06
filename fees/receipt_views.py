"""
Additional views for PDF receipt download
"""
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from .models import Payment
from .receipts import PaymentReceiptGenerator


@login_required
def download_payment_receipt(request, payment_id):
    """Generate and download PDF receipt for a payment"""
    # Get payment - students can only download their own receipts
    if request.user.is_staff or request.user.is_superuser:
        # Admin can download any receipt
        payment = get_object_or_404(Payment, pk=payment_id, school=request.school)
    else:
        # Student can only download their own
        payment = get_object_or_404(
            Payment,
            pk=payment_id,
            student__student=request.user,
            school=request.school
        )
    
    # Only allow downloads for verified payments
    if payment.status != 'VERIFIED':
        return HttpResponse("Receipt not available - payment not yet verified", status=403)
    
    # Generate PDF
    generator = PaymentReceiptGenerator(payment)
    pdf_buffer = generator.generate()
    
    # Create response
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{payment.id}_{payment.payment_date}.pdf"'
    
    return response
