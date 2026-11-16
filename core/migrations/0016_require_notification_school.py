from django.db import migrations, models
import django.db.models.deletion


def assign_schools(apps, schema_editor):
    """Backfill notifications created before the school field was required."""
    Notification = apps.get_model("core", "Notification")
    School = apps.get_model("school", "School")

    fallback_school = School.objects.order_by("pk").first()
    unscoped = Notification.objects.filter(school__isnull=True).select_related(
        "recipient", "actor"
    )

    for notification in unscoped:
        school_id = None
        if notification.recipient_id:
            school_id = notification.recipient.school_id
        if school_id is None and notification.actor_id:
            school_id = notification.actor.school_id
        if school_id is None and fallback_school is not None:
            school_id = fallback_school.pk

        # There is no safe tenant to attach an orphaned notification to.
        if school_id is None:
            notification.delete()
            continue

        notification.school_id = school_id
        notification.save(update_fields=["school"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_alter_newsandevents_summary_and_more"),
    ]

    operations = [
        migrations.RunPython(assign_schools, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notification",
            name="school",
            field=models.ForeignKey(
                help_text="Every notification belongs to exactly one school.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="notifications",
                to="school.school",
                verbose_name="School",
            ),
        ),
    ]
