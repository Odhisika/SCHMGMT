from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="division",
            field=models.CharField(
                blank=True,
                help_text="Optional division restriction for this notification.",
                max_length=25,
                verbose_name="Division",
            ),
        ),
    ]
