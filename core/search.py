"""Helpers for forgiving, multi-word search filters.

A user searching for ``"Ama Mensah"`` expects to find the person whose first
name is *Ama* and last name is *Mensah*. A plain ``icontains`` lookup on each
field only matches when the whole phrase appears in a single field, so full
names (and reordered keywords such as ``"Nursery Quiz"``) silently returned
nothing. The helpers below split a query into words and require every word to
match at least one field.
"""

from django.db.models import Q

# Punctuation users commonly type around search terms (including the ``#``
# prefixes used by the old search placeholder).
_TRIM_CHARACTERS = "#,.;:!?()[]{}\"'"


def tokenize_query(query):
    """Split ``query`` into meaningful words, dropping punctuation-only noise."""
    tokens = []
    for raw in (query or "").split():
        token = raw.strip(_TRIM_CHARACTERS)
        if token:
            tokens.append(token)
    return tokens


def build_search_query(query, fields):
    """Build a ``Q`` object requiring every query word to match a field.

    ``fields`` is an iterable of ORM lookup paths, for example
    ``["first_name", "last_name", "email"]``. Each word may match any one of
    the fields, so the order of words in the query does not matter.
    """
    tokens = tokenize_query(query)
    if not tokens:
        return Q()

    criteria = Q()
    for token in tokens:
        token_q = Q()
        for field in fields:
            token_q |= Q(**{f"{field}__icontains": token})
        criteria &= token_q
    return criteria
