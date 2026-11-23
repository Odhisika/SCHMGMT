from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from accounts.models import STUDENT_STATUS_ACTIVE, Student
from core.models import Term
from .models import FeeStructure, StudentFeeAssignment, StudentPaymentReference
from .utils import fee_matches_student


def resolve_fee_term(school, term_code=None):
    """Find the Term a fee should be assigned to.

    A fee with no term uses the school's current term.  A named term uses the
    most recent matching term, preferring the current one when several years
    exist.  If the named term has not been created yet we fall back to the
    current term so the fee is still visible to students.
    """
    terms = Term.objects.filter(school=school)
    if term_code:
        matching = terms.filter(term=term_code).order_by('-is_current_term', '-year')
        return matching.first() or terms.filter(is_current_term=True).first()
    return terms.filter(is_current_term=True).first()


@receiver(post_save, sender=FeeStructure)
def auto_assign_fees_to_students(sender, instance, created, **kwargs):
    """Create assignments for students in the fee structure's scope.

    Also runs on updates so changing a fee's division/class immediately
    affects the students in the newly selected scope.
    """
    if kwargs.get('raw', False) or not instance.auto_assign or not instance.is_active:
        return

    term = resolve_fee_term(instance.school, instance.term)
    if not term:
        return

    students = Student.objects.filter(
        student__school=instance.school,
        status=STUDENT_STATUS_ACTIVE,
    ).select_related('student')

    matching = [student for student in students if fee_matches_student(instance, student)]
    if not matching:
        return

    with transaction.atomic():
        StudentFeeAssignment.objects.bulk_create(
            [
                StudentFeeAssignment(
                    student=student,
                    fee_structure=instance,
                    term=term,
                    amount=instance.amount,
                )
                for student in matching
            ],
            ignore_conflicts=True,
        )


@receiver(post_save, sender=Student)
def create_payment_reference(sender, instance, created, **kwargs):
    """Automatically create a unique payment reference when student is created."""
    if created and not hasattr(instance, 'payment_reference'):
        StudentPaymentReference.objects.create(student=instance)


@receiver(post_save, sender=Student)
def assign_fees_on_enrollment(sender, instance, created, **kwargs):
    """Assign active auto-assign fees to a student when they are enrolled."""
    if kwargs.get('raw', False) or not created or instance.status != STUDENT_STATUS_ACTIVE:
        return

    school = getattr(instance.student, 'school', None)
    if not school:
        return

    fee_structures = FeeStructure.objects.filter(
        school=school,
        is_active=True,
        auto_assign=True,
    ).select_related('school')

    with transaction.atomic():
        for fee in fee_structures:
            if not fee_matches_student(fee, instance):
                continue

            term = resolve_fee_term(fee.school, fee.term)
            if not term:
                continue

            StudentFeeAssignment.objects.get_or_create(
                student=instance,
                fee_structure=fee,
                term=term,
                defaults={'amount': fee.amount},
            )
