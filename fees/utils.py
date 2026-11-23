"""Helpers for resolving which students a fee structure applies to.

Fee structures historically only had a ``level``.  Empty meant "all levels".
With school-defined divisions we also need "all classes in this division", so
``division`` + ``level`` combine as follows:

* division blank, class blank      -> every class in the school
* division set, class blank        -> every class in that division
* division set, class set          -> that one class in that division
* division blank, class set        -> legacy single-class targeting
"""

from school.division_utils import get_division_for_level


def fee_matches_student(fee, student):
    """Return True when ``student`` is inside the fee structure's scope."""
    school = getattr(fee, "school", None)

    if fee.division:
        student_division = get_division_for_level(student.level, school=school)
        if student_division != fee.division:
            return False

    if fee.level and fee.level != student.level:
        return False

    return True
