"""Annual student promotion engine.

The promotion decision is based on a learner's average across the three terms
of the academic session. The rules come from the school's ``PromotionPolicy``
so the UI and the ``promote_students`` management command always agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from accounts.models import Student, User
from core.models import Term
from course.models import Program

from .models import PROMOTION_STATUS_CHOICES, Result


@dataclass
class PromotionCandidate:
    """One learner's annual promotion evaluation."""

    student: Student
    level: str
    term1: Decimal | None
    term2: Decimal | None
    term3: Decimal | None
    average: Decimal
    status: str
    next_level: str | None
    is_graduating: bool
    promoted: bool
    result: Result | None = None

    @property
    def action(self):
        if self.promoted and self.is_graduating:
            return "Graduate"
        if self.promoted:
            return f"Promote to {self.next_level}"
        return "Repeat"

    @property
    def status_label(self):
        return str(dict(PROMOTION_STATUS_CHOICES).get(self.status, self.status))

    @property
    def status_color(self):
        return {
            "AUTO_PASS": "success",
            "MANUAL_PASS": "success",
            "AUTO_FAIL": "danger",
            "MANUAL_FAIL": "danger",
            "BORDERLINE": "warning",
            "PENDING": "secondary",
        }.get(self.status, "secondary")


def next_level(current_level):
    """Return the next class level, or ``None`` for the final class."""
    levels = [level for level, _ in settings.LEVEL_CHOICES]
    try:
        index = levels.index(current_level)
    except ValueError:
        return None
    if index + 1 < len(levels):
        return levels[index + 1]
    return None


def division_for_level(level):
    for division, levels in settings.DIVISION_LEVEL_MAPPING.items():
        if level in levels:
            return division
    return None


def _term_results(student, session, level, school):
    results = Result.objects.filter(
        student=student,
        session=session,
        level=level,
        school=school,
    )
    return {result.term: result for result in results}


def _evaluate(policy, average):
    if policy is not None:
        return policy.evaluate(average)
    if average >= Decimal("50.00"):
        return "AUTO_PASS"
    if average < Decimal("40.00"):
        return "AUTO_FAIL"
    return "BORDERLINE"


def build_candidates(level, session, school, policy=None):
    """Evaluate every learner in ``level`` for the given academic session."""
    if policy is None:
        policy = getattr(school, "promotion_policy", None)

    students = (
        Student.objects.filter(level=level, student__school=school)
        .select_related("student", "program")
        .order_by("student__last_name", "student__first_name", "student__username")
    )

    candidates = []
    for student in students:
        per_term = _term_results(student, session, level, school)
        t1 = per_term.get(settings.FIRST_TERM)
        t2 = per_term.get(settings.SECOND_TERM)
        t3 = per_term.get(settings.THIRD_TERM)

        def score(result):
            return result.term_average if result and result.term_average is not None else Decimal("0.00")

        average = round(
            (score(t1) + score(t2) + score(t3)) / Decimal("3"), 2
        )
        status = _evaluate(policy, average)

        # A manual decision (promotion request) wins over the automatic one.
        if t3 and t3.promotion_status in ("MANUAL_PASS", "MANUAL_FAIL"):
            status = t3.promotion_status

        promoted = status in ("AUTO_PASS", "MANUAL_PASS")
        upcoming = next_level(level)

        candidates.append(
            PromotionCandidate(
                student=student,
                level=level,
                term1=t1.term_average if t1 else None,
                term2=t2.term_average if t2 else None,
                term3=t3.term_average if t3 else None,
                average=average,
                status=status,
                next_level=upcoming,
                is_graduating=upcoming is None,
                promoted=promoted,
                result=t3,
            )
        )

    return candidates


def _move_student(student, target_level, school):
    """Move a learner to the next class without re-running enrolment signals."""
    target_division = division_for_level(target_level)
    program = (
        Program.objects.filter(
            school=school,
            division=target_division,
            is_academic_block=True,
        ).first()
        or student.program
    )

    Student.objects.filter(pk=student.pk).update(
        level=target_level,
        program=program,
    )
    if target_division and student.student.division != target_division:
        User.objects.filter(pk=student.student_id).update(
            division=target_division
        )

    student.level = target_level
    student.program = program


def apply_promotion(candidates):
    """Persist promotion statuses and move successful learners up a class."""
    promoted = 0
    graduated = 0
    held_back = 0

    for candidate in candidates:
        if candidate.result is not None:
            candidate.result.promotion_status = candidate.status
            candidate.result.save(
                update_fields=["promotion_status", "promoted"]
            )

        if not candidate.promoted:
            held_back += 1
            continue

        if candidate.is_graduating:
            graduated += 1
            continue

        _move_student(
            candidate.student, candidate.next_level, candidate.student.student.school
        )
        promoted += 1

    return {
        "promoted": promoted,
        "graduated": graduated,
        "held_back": held_back,
    }


def session_for_current_term(school):
    current_term = Term.objects.filter(
        school=school, is_current_term=True
    ).first()
    return current_term.year if current_term else None
