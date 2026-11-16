"""Annual student promotion and final-class completion engine.

Promotion decisions are based on a learner's average across the terms that
have actually been recorded for the academic session.  A missing term is never
treated as a zero.

The final class (normally JHS 3) is different from other classes: learners sit
BECE and normally leave before a full Third Term.  They are therefore marked
*graduated* rather than promoted, and their average is calculated over the
available terms (usually First and Second).  BECE results are handled by WAEC
and are not required by this engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from accounts.models import (
    STUDENT_STATUS_ACTIVE,
    STUDENT_STATUS_GRADUATED,
    Student,
    User,
)
from core.models import Term
from course.models import Program

from .models import PROMOTION_STATUS_CHOICES, PromotionDecision, Result


TERM_ORDER = {
    settings.FIRST_TERM: 1,
    settings.SECOND_TERM: 2,
    settings.THIRD_TERM: 3,
}


def term_rank(term_name):
    """Return the 1-based position of a term, or 0 for an unknown term."""
    return TERM_ORDER.get(term_name, 0)


@dataclass
class PromotionCandidate:
    """One learner's annual promotion or completion evaluation."""

    student: Student
    school: object
    level: str
    session: str
    term1: Decimal | None
    term2: Decimal | None
    term3: Decimal | None
    terms_used: int
    terms_present: tuple[str, ...]
    average: Decimal | None
    status: str
    next_level: str | None
    is_final_class: bool
    is_graduating: bool
    promoted: bool
    decision: str
    result: Result | None = None
    exit_date: object | None = None

    @property
    def action(self):
        if self.is_graduating:
            if self.promoted:
                return "Graduate"
            return "Hold / Review"
        if self.status == "INCOMPLETE":
            return "Review"
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
            "COMPLETED": "success",
            "AUTO_FAIL": "danger",
            "MANUAL_FAIL": "danger",
            "BORDERLINE": "warning",
            "INCOMPLETE": "warning",
            "PENDING": "secondary",
        }.get(self.status, "secondary")

    @property
    def average_display(self):
        if self.average is None:
            return "-"
        return f"{self.average:.2f}"

    @property
    def term3_display(self):
        if self.term3 is not None:
            return f"{self.term3}"
        return "N/A" if self.is_final_class else "-"

    @property
    def terms_label(self):
        if not self.terms_present:
            return "No results"
        return ", ".join(self.terms_present)


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


def is_final_class(level):
    """Return True when ``level`` has no next class in this school."""
    return next_level(level) is None


def division_for_level(level):
    for division, levels in settings.DIVISION_LEVEL_MAPPING.items():
        if level in levels:
            return division
    return None


def _term_results(student, session, level, school):
    """Return the best result for each term in ``session``.

    A learner can occasionally have results tagged with more than one level in
    the same session (for example after a mid-year level correction).  Prefer
    the result matching the level being evaluated, while still allowing a
    result recorded under another level to count.
    """
    results = Result.objects.filter(
        student=student,
        session=session,
        school=school,
    )
    per_term = {}
    for result in results.order_by("id"):
        current = per_term.get(result.term)
        if current is None or (
            result.level == level and current.level != level
        ):
            per_term[result.term] = result
    return per_term


def _manual_status(per_term, student, session, school):
    """Return a manual override from term results or an earlier decision.

    For final-class learners, MANUAL_FAIL is treated as an administrative hold
    (not an academic repeat) via the returned status.
    """
    for term_name in (
        settings.THIRD_TERM,
        settings.SECOND_TERM,
        settings.FIRST_TERM,
    ):
        result = per_term.get(term_name)
        if result and result.promotion_status in ("MANUAL_PASS", "MANUAL_FAIL"):
            return result.promotion_status

    decision = PromotionDecision.objects.filter(
        student=student,
        school=school,
        session=session,
    ).first()
    if decision and decision.status in ("MANUAL_PASS", "MANUAL_FAIL", "INCOMPLETE"):
        return decision.status
    return None


def _term_end_date(school, session, terms_present):
    """Use the end date of the latest term that has a result."""
    for term_name in reversed(terms_present):
        term = Term.objects.filter(
            school=school,
            year=session,
            term=term_name,
        ).first()
        if term and term.end_date:
            return term.end_date
    return None


def _evaluate(policy, average):
    if policy is not None:
        return policy.evaluate(average)
    if average >= Decimal("50.00"):
        return "AUTO_PASS"
    if average < Decimal("40.00"):
        return "AUTO_FAIL"
    return "BORDERLINE"


def build_candidates(level, session, school, policy=None):
    """Evaluate every active learner in ``level`` for ``session``."""
    if policy is None:
        policy = getattr(school, "promotion_policy", None)

    students = (
        Student.objects.filter(
            level=level,
            student__school=school,
            status=STUDENT_STATUS_ACTIVE,
        )
        .select_related("student", "program")
        .order_by("student__last_name", "student__first_name", "student__username")
    )

    final_class = is_final_class(level)
    candidates = []
    for student in students:
        per_term = _term_results(student, session, level, school)
        t1 = per_term.get(settings.FIRST_TERM)
        t2 = per_term.get(settings.SECOND_TERM)
        t3 = per_term.get(settings.THIRD_TERM)

        scores = []
        terms_present = []
        for term_name in (
            settings.FIRST_TERM,
            settings.SECOND_TERM,
            settings.THIRD_TERM,
        ):
            result = per_term.get(term_name)
            if result and result.term_average is not None:
                scores.append(result.term_average)
                terms_present.append(term_name)

        terms_used = len(scores)
        average = (
            round(sum(scores, Decimal("0.00")) / Decimal(terms_used), 2)
            if terms_used
            else None
        )

        manual = _manual_status(per_term, student, session, school)

        if manual is not None:
            if final_class and manual == "MANUAL_FAIL":
                # No academic repeat in JHS 3; treat as an administrative hold.
                status = "INCOMPLETE"
                promoted = False
            elif manual == "INCOMPLETE":
                status = "INCOMPLETE"
                promoted = False
            else:
                status = manual
                promoted = manual == "MANUAL_PASS"
        elif average is None:
            status = "INCOMPLETE"
            promoted = False
        elif final_class:
            # JHS 3/final class does not have academic repetition.  Any learner
            # with a valid school record is completed/graduated (BECE is handled
            # by WAEC).  If BECE registration/completion is administratively held
            # (illness, fees, school decision, etc.), keep the learner active as
            # needing review rather than marking them as a repeater.
            status = "COMPLETED"
            promoted = True
        elif terms_used < 3:
            # Do not auto-fail a learner simply because a term is missing.
            status = "INCOMPLETE"
            promoted = False
        else:
            status = _evaluate(policy, average)
            promoted = status == "AUTO_PASS"

        # Final class can only be graduated or held for review — never repeated.
        if final_class and not promoted:
            status = "INCOMPLETE"
            decision = "REVIEW"
        elif final_class and promoted:
            status = "COMPLETED" if status not in ("MANUAL_PASS",) else status
            decision = "GRADUATE"
        elif status == "INCOMPLETE":
            decision = "REVIEW"
        elif promoted:
            decision = "PROMOTE"
        else:
            decision = "REPEAT"

        upcoming = next_level(level)
        latest = t3 or t2 or t1

        candidates.append(
            PromotionCandidate(
                student=student,
                school=school,
                level=level,
                session=session,
                term1=t1.term_average if t1 else None,
                term2=t2.term_average if t2 else None,
                term3=t3.term_average if t3 else None,
                terms_used=terms_used,
                terms_present=tuple(terms_present),
                average=average,
                status=status,
                next_level=upcoming,
                is_final_class=final_class,
                is_graduating=final_class,
                promoted=promoted,
                decision=decision,
                result=latest,
                exit_date=_term_end_date(school, session, terms_present),
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


def apply_promotion(candidates, decided_by=None):
    """Persist decisions and move or graduate successful learners."""
    promoted = 0
    graduated = 0
    held_back = 0
    incomplete = 0
    now = timezone.now()

    for candidate in candidates:
        PromotionDecision.objects.update_or_create(
            student=candidate.student,
            school=candidate.school,
            session=candidate.session,
            defaults={
                "level": candidate.level,
                "next_level": candidate.next_level,
                "term1": candidate.term1,
                "term2": candidate.term2,
                "term3": candidate.term3,
                "terms_used": candidate.terms_used,
                "average": candidate.average,
                "is_final_class": candidate.is_final_class,
                "status": candidate.status,
                "decision": candidate.decision,
                "decided_by": decided_by,
            },
        )

        if candidate.result is not None and candidate.status != "INCOMPLETE":
            candidate.result.promotion_status = candidate.status
            candidate.result.save(
                update_fields=["promotion_status", "promoted"],
                update_position=False,
            )

        if not candidate.promoted:
            if candidate.status == "INCOMPLETE":
                incomplete += 1
            else:
                held_back += 1
            continue

        if candidate.is_final_class:
            Student.objects.filter(pk=candidate.student.pk).update(
                status=STUDENT_STATUS_GRADUATED,
                status_changed_at=now,
                exit_session=candidate.session,
                exit_date=candidate.exit_date,
            )
            candidate.student.status = STUDENT_STATUS_GRADUATED
            graduated += 1
        else:
            _move_student(
                candidate.student,
                candidate.next_level,
                candidate.school,
            )
            promoted += 1

    return {
        "promoted": promoted,
        "graduated": graduated,
        "held_back": held_back,
        "incomplete": incomplete,
    }


def session_for_current_term(school):
    current_term = Term.objects.filter(
        school=school, is_current_term=True
    ).first()
    return current_term.year if current_term else None
