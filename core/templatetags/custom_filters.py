from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def unique_messages(messages):
    """Remove repeated flash messages while preserving their original order.

    Permission decorators can add the same "Access denied" notice several
    times while a user navigates between restricted pages. Showing it once is
    enough and avoids stacking identical alerts at the top of a page.
    """
    seen = set()
    unique = []
    for message in messages or []:
        key = (getattr(message, "level", None), str(message))
        if key in seen:
            continue
        seen.add(key)
        unique.append(message)
    return unique
