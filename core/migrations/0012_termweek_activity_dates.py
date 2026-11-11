# Generated for explicit calendar dates on weekly term activities.
import datetime

from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


def populate_week_dates(apps, schema_editor):
    TermWeek = apps.get_model("core", "TermWeek")

    for week in TermWeek.objects.select_related("term").iterator():
        term = week.term
        if not term.start_date:
            continue

        start_date = term.start_date + datetime.timedelta(days=(week.week_number - 1) * 7)
        if term.end_date and start_date > term.end_date:
            continue
        end_date = start_date + datetime.timedelta(days=6)
        if term.end_date:
            end_date = min(end_date, term.end_date)
        week.start_date = start_date
        week.end_date = end_date
        week.save(update_fields=["start_date", "end_date"])


class Migration(migrations.Migration):
    dependencies = [("core", "0011_termweek")]

    operations = [
        migrations.AddField(
            model_name="termweek",
            name="start_date",
            field=models.DateField(blank=True, null=True, verbose_name=_("Activity Start Date")),
        ),
        migrations.AddField(
            model_name="termweek",
            name="end_date",
            field=models.DateField(blank=True, null=True, verbose_name=_("Activity End Date")),
        ),
        migrations.RunPython(populate_week_dates, migrations.RunPython.noop),
    ]
