from django.db import migrations

# Point-in-time snapshot of the level -> division mapping from settings.
LEVEL_TO_DIVISION = {
    "Nursery 1": "Nursery",
    "Nursery 2": "Nursery",
    "KG 1": "Nursery",
    "KG 2": "Nursery",
    "Primary 1": "Primary",
    "Primary 2": "Primary",
    "Primary 3": "Primary",
    "Primary 4": "Primary",
    "Primary 5": "Primary",
    "Primary 6": "Primary",
    "JHS 1": "JHS",
    "JHS 2": "JHS",
    "JHS 3": "JHS",
}


def backfill_student_division(apps, schema_editor):
    """Set the user's division from the student's level for existing students.

    Students created before the division sync in Student.save() have a NULL
    division on their user row, which makes them invisible on views that
    group students by division (e.g. the student list tabs).
    """
    User = apps.get_model("accounts", "User")
    Student = apps.get_model("accounts", "Student")

    for student in Student.objects.select_related("student").exclude(level=None):
        division = LEVEL_TO_DIVISION.get(student.level)
        user = student.student
        if division and user.division != division:
            user.division = division
            user.save(update_fields=["division"])


def unbackfill_student_division(apps, schema_editor):
    """No-op: restoring NULL divisions would hide students again."""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_user_division_alter_student_level_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_student_division, unbackfill_student_division),
    ]
