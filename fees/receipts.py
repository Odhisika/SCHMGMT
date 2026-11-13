"""
PDF Receipt Generator for Student Payments
Redesigned with the elegant school frame design dynamically themed to the school's native colors.
"""
import os
from decimal import Decimal
from io import BytesIO
from django.conf import settings
from django.template.loader import get_template
from xhtml2pdf import pisa
from core.pdf_utils import link_callback, get_school_document_frame, clean_hex_color


class PaymentReceiptGenerator:
    """Generate PDF receipts for student payments"""

    def __init__(self, payment):
        self.payment = payment
        self.buffer = BytesIO()

    def generate(self):
        """Generate the redesigned PDF receipt"""
        school = self.payment.school
        frame_path = get_school_document_frame(school)
        primary_color = clean_hex_color(getattr(school, "primary_color", None), "#0c2340")
        secondary_color = clean_hex_color(getattr(school, "secondary_color", None), "#7cb342")
        accent_color = clean_hex_color(getattr(school, "accent_color", None), "#f59e0b")

        logo_path = None
        if getattr(school, "logo", None) and school.logo:
            try:
                if os.path.exists(school.logo.path):
                    logo_path = school.logo.path
            except Exception:
                pass

        # Embedded fonts that include the cedi sign (U+20B5). The default
        # Helvetica font used by xhtml2pdf does not, so "GH₵" renders as a box.
        font_regular = os.path.join(
            settings.BASE_DIR, "static", "fonts", "dejavu", "DejaVuSans.ttf"
        )
        font_bold = os.path.join(
            settings.BASE_DIR, "static", "fonts", "dejavu", "DejaVuSans-Bold.ttf"
        )

        # Payment reference code
        payment_reference = None
        try:
            payment_reference = self.payment.student.payment_reference.reference_code
        except Exception:
            pass
        if not payment_reference and getattr(self.payment, "paystack_reference", None):
            payment_reference = self.payment.paystack_reference

        # Fee structure & billing calculations
        fee_title = "School Tuition & Facility Fees"
        billed_amount = self.payment.amount
        remaining_balance = None

        if self.payment.assignment:
            if getattr(self.payment.assignment, "fee_structure", None):
                fee_title = self.payment.assignment.fee_structure.name
            billed_amount = getattr(self.payment.assignment, "amount", self.payment.amount)

            # Compute remaining balance for this assignment
            try:
                from .models import Payment
                total_verified = sum(
                    p.amount
                    for p in Payment.objects.filter(
                        assignment=self.payment.assignment, status="VERIFIED"
                    )
                )
                remaining_balance = max(Decimal("0.00"), billed_amount - total_verified)
            except Exception:
                pass

        context = {
            "payment": self.payment,
            "school": school,
            "receipt_number": self.payment.receipt_number or f"RCP-{self.payment.id:06d}",
            "payment_reference": payment_reference,
            "fee_title": fee_title,
            "billed_amount": billed_amount,
            "remaining_balance": remaining_balance,
            "background_image_path": frame_path,
            "logo_path": logo_path,
            "font_regular": font_regular if os.path.exists(font_regular) else "",
            "font_bold": font_bold if os.path.exists(font_bold) else "",
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "accent_color": accent_color,
            "title": f"Fee Receipt - {self.payment.receipt_number or self.payment.id}",
        }

        template = get_template("fees/payment_receipt_pdf.html")
        html = template.render(context)
        pisa_status = pisa.CreatePDF(html, dest=self.buffer, link_callback=link_callback)
        if pisa_status.err:
            pass

        self.buffer.seek(0)
        return self.buffer
