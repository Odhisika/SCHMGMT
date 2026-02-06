from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal

from accounts.models import Student
from core.models import Term
from .models import FeeStructure, StudentFeeAssignment, StudentPaymentReference


@receiver(post_save, sender=FeeStructure)
def auto_assign_fees_to_students(sender, instance, created, **kwargs):
    """
    Automatically create fee assignments when a fee structure is created.
    Only runs if auto_assign is True and level is specified.
    """
    # Only auto-assign on creation and if auto_assign is enabled
    if not created or not instance.auto_assign or not instance.level:
        return
    
    # Get current term or the specified term
    if instance.term:
        # If term is specified in fee structure, find matching Term object
        current_term = Term.objects.filter(
            school=instance.school,
            is_current_term=True
        ).first()
    else:
        current_term = Term.objects.filter(
            school=instance.school,
            is_current_term=True
        ).first()
    
    if not current_term:
        return
    
    # Get all students in the specified level and school
    students = Student.objects.filter(
        student__school=instance.school,
        level=instance.level
    )
    
    # Create assignments in bulk for better performance
    assignments = []
    for student in students:
        # Check if assignment already exists
        existing = StudentFeeAssignment.objects.filter(
            student=student,
            fee_structure=instance,
            term=current_term
        ).exists()
        
        if not existing:
            assignments.append(
                StudentFeeAssignment(
                    student=student,
                    fee_structure=instance,
                    term=current_term,
                    amount=instance.amount
                )
            )
    
    # Bulk create assignments
    if assignments:
        with transaction.atomic():
            StudentFeeAssignment.objects.bulk_create(assignments)


@receiver(post_save, sender=Student)
def create_payment_reference(sender, instance, created, **kwargs):
    """
    Automatically create a unique payment reference when student is created.
    """
    if created:
        # Check if reference already exists
        if not hasattr(instance, 'payment_reference'):
            StudentPaymentReference.objects.create(student=instance)


@receiver(post_save, sender=Student)
def assign_fees_on_enrollment(sender, instance, created, **kwargs):
    """
    Automatically assign fees to students when they are created or when
    their level changes.
    """
    # Skip if this is being loaded from a fixture
    if kwargs.get('raw', False):
        return
    
    # Get the student's school
    school = instance.student.school
    if not school:
        return
    
    # Get current term
    current_term = Term.objects.filter(is_current_term=True, school=school).first()
    if not current_term:
        return
    
    # Find all fee structures that should be auto-assigned to this student
    from django.db import models
    fee_structures = FeeStructure.objects.filter(
        school=school,
        is_active=True,
        auto_assign=True
    ).filter(
        # Match level (or blank for all levels)
        models.Q(level=instance.level) | models.Q(level='')
    ).filter(
        # Match term (or blank for all terms)
        models.Q(term=current_term.term) | models.Q(term='')
    )
    
    # Assign fees to student
    assignments = []
    for fee_structure in fee_structures:
        # Check if assignment already exists
        existing = StudentFeeAssignment.objects.filter(
            student=instance,
            fee_structure=fee_structure,
            term=current_term
        ).exists()
        
        if not existing:
            assignments.append(
                StudentFeeAssignment(
                    student=instance,
                    fee_structure=fee_structure,
                    term=current_term,
                    amount=fee_structure.amount
                )
            )
    
    # Bulk create assignments
    if assignments:
        with transaction.atomic():
            StudentFeeAssignment.objects.bulk_create(assignments)
