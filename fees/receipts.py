"""
PDF Receipt Generator for Student Payments
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from io import BytesIO
from django.conf import settings
from datetime import datetime


class PaymentReceiptGenerator:
    """Generate PDF receipts for student payments"""
    
    def __init__(self, payment):
        self.payment = payment
        self.buffer = BytesIO()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            name='SchoolHeader',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a73e8'),
            alignment=TA_CENTER,
            spaceAfter=6,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='ReceiptTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#202124'),
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            fontSize=11,
            textColor=colors.HexColor('#5f6368'),
            spaceAfter=8,
            fontName='Helvetica-Bold'
        ))
    
    def generate(self):
        """Generate the PDF receipt"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        # Build PDF content
        story = []
        
        # Header
        story.extend(self._build_header())
        story.append(Spacer(1, 0.3*inch))
        
        # Receipt Info
        story.extend(self._build_receipt_info())
        story.append(Spacer(1, 0.2*inch))
        
        # Student Details
        story.extend(self._build_student_details())
        story.append(Spacer(1, 0.2*inch))
        
        # Payment Details
        story.extend(self._build_payment_details())
        story.append(Spacer(1, 0.3*inch))
        
        # Footer
        story.extend(self._build_footer())
        
        # Build PDF
        doc.build(story)
        self.buffer.seek(0)
        return self.buffer
    
    def _build_header(self):
        """Build school header"""
        elements = []
        
        # School name
        school_name = self.payment.school.name
        elements.append(Paragraph(school_name, self.styles['SchoolHeader']))
        
        # School address if available
        if hasattr(self.payment.school, 'address') and self.payment.school.address:
            address_style = ParagraphStyle(
                'Address',
                parent=self.styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#5f6368'),
                alignment=TA_CENTER
            )
            elements.append(Paragraph(self.payment.school.address, address_style))
        
        return elements
    
    def _build_receipt_info(self):
        """Build receipt information section"""
        elements = []
        
        elements.append(Paragraph("PAYMENT RECEIPT", self.styles['ReceiptTitle']))
        
        # Receipt details table
        receipt_data = [
            ['Receipt No:', self.payment.receipt_number or f"RCP-{self.payment.id}"],
            ['Date Issued:', datetime.now().strftime('%B %d, %Y')],
            ['Payment Date:', self.payment.payment_date.strftime('%B %d, %Y')],
        ]
        
        receipt_table = Table(receipt_data, colWidths=[2*inch, 3*inch])
        receipt_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#5f6368')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(receipt_table)
        return elements
    
    def _build_student_details(self):
        """Build student details section"""
        elements = []
        
        elements.append(Paragraph("Student Information", self.styles['SectionHeader']))
        
        student = self.payment.student
        student_data = [
            ['Name:', student.student.get_full_name()],
            ['Student ID:', student.student.username],
            ['Class/Level:', student.level or 'N/A'],
        ]
        
        # Add payment reference if available
        try:
            payment_ref = student.payment_reference.reference_code
            student_data.append(['Payment Reference:', payment_ref])
        except:
            pass
        
        student_table = Table(student_data, colWidths=[2*inch, 3*inch])
        student_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#5f6368')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ]))
        
        elements.append(student_table)
        return elements
    
    def _build_payment_details(self):
        """Build payment details section"""
        elements = []
        
        elements.append(Paragraph("Payment Details", self.styles['SectionHeader']))
        
        # Payment info table
        payment_data = [
            ['Payment Method:', self.payment.get_payment_method_display()],
            ['Status:', self.payment.get_status_display()],
        ]
        
        if self.payment.assignment:
            payment_data.append(['Fee Type:', self.payment.assignment.fee_structure.name])
        
        payment_table = Table(payment_data, colWidths=[2*inch, 3*inch])
        payment_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#5f6368')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(payment_table)
        elements.append(Spacer(1, 0.2*inch))
        
        # Amount paid (highlighted)
        amount_data = [
            ['Amount Paid:', f'GH₵{self.payment.amount}']
        ]
        
        amount_table = Table(amount_data, colWidths=[2*inch, 3*inch])
        amount_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1a73e8')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1a73e8')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e8f0fe')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1a73e8')),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ]))
        
        elements.append(amount_table)
        return elements
    
    def _build_footer(self):
        """Build receipt footer"""
        elements = []
        
        # Thank you message
        thank_you_style = ParagraphStyle(
            'ThankYou',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#5f6368'),
            alignment=TA_CENTER,
            spaceAfter=20
        )
        elements.append(Paragraph("Thank you for your payment!", thank_you_style))
        
        # Signature line
        elements.append(Spacer(1, 0.5*inch))
        
        sig_data = [
            ['_' * 30, '', '_' * 30],
            ['Bursar/Accountant', '', 'School Stamp']
        ]
        
        sig_table = Table(sig_data, colWidths=[2.2*inch, 0.6*inch, 2.2*inch])
        sig_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#5f6368')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 1), (-1, 1), 0),
        ]))
        
        elements.append(sig_table)
        
        # Note
        note_style = ParagraphStyle(
            'Note',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#5f6368'),
            alignment=TA_CENTER,
            leftIndent=0.5*inch,
            rightIndent=0.5*inch
        )
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph(
            "<i>This is a computer-generated receipt and is valid without signature. "
            "For inquiries, please contact the school administration.</i>",
            note_style
        ))
        
        return elements
