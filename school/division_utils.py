"""Helpers that combine the built-in divisions with a school's custom ones.

The rest of the app historically reads the three global divisions directly from
``settings``.  These helpers keep that behaviour while allowing each school to
add extra divisions and classes from School Settings and arrange them in the
order that makes sense for that school.
"""

from django.conf import settings


def _custom_divisions(school):
    if not school or not getattr(school, "pk", None):
        return []
    return list(
        school.custom_divisions.filter(is_active=True)
        .prefetch_related("levels")
        .order_by("order", "name")
    )


def _built_in_divisions():
    return [(value, label) for value, label in settings.DIVISION_CHOICES]


def _ordered_division_details(school):
    """Return ``(name, label, is_built_in)`` in the school's display order.

    New custom divisions default to the front, so a school that adds Creche
    immediately sees Creche, Nursery, Primary, JHS.  An administrator can
    override the order using ``SchoolDivisionOrder`` rows.
    """
    custom = _custom_divisions(school)
    built_in = _built_in_divisions()

    base = [(division.name, division.name, False) for division in custom]
    base.extend((name, label, True) for name, label in built_in)

    # De-duplicate defensively (a school cannot normally create duplicate names).
    details = []
    seen = set()
    for item in base:
        if item[0] not in seen:
            seen.add(item[0])
            details.append(item)

    placements = {}
    if school and getattr(school, "pk", None):
        placements = {
            placement.division: placement.order
            for placement in school.division_order.all()
        }
    fallback = {name: index for index, (name, _, _) in enumerate(details)}

    return sorted(
        details,
        key=lambda item: (placements.get(item[0], fallback[item[0]]), fallback[item[0]]),
    )


def get_division_choices(school=None):
    """Return ``(value, label)`` division choices in display order."""
    return tuple(
        (name, label) for name, label, _ in _ordered_division_details(school)
    )


def get_division_level_mapping(school=None):
    """Return the division -> levels mapping in display order."""
    built_in_mapping = {
        division: list(levels)
        for division, levels in settings.DIVISION_LEVEL_MAPPING.items()
    }
    custom_levels = {
        division.name: [
            (level.name, level.name)
            for level in division.levels.filter(is_active=True).order_by("order", "name")
        ]
        for division in _custom_divisions(school)
    }

    mapping = {}
    for name, _, _ in _ordered_division_details(school):
        if name in built_in_mapping:
            mapping[name] = built_in_mapping[name]
        elif name in custom_levels:
            mapping[name] = custom_levels[name]
    return mapping


def _level_codes(levels):
    """Normalize both the legacy string list and the new (code, label) list."""
    if levels and isinstance(levels[0], (tuple, list)):
        return [code for code, _ in levels]
    return list(levels)


def get_level_choices(school=None):
    """Return all class levels available to a school, in display order."""
    labels = dict(settings.LEVEL_CHOICES)
    choices = []
    known = set()
    for levels in get_division_level_mapping(school).values():
        for code in _level_codes(levels):
            if code not in known:
                choices.append((code, labels.get(code, code)))
                known.add(code)
    return tuple(choices)


def get_division_for_level(level_code, school=None):
    """Find the division that owns ``level_code`` for the given school."""
    if not level_code:
        return None
    for division, levels in get_division_level_mapping(school).items():
        if level_code in _level_codes(levels):
            return division
    return None


def get_levels_for_division(division, school=None):
    """Return the class levels in ``division`` for the given school."""
    return _level_codes(get_division_level_mapping(school).get(division, []))
