from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("school", "0004_school_student_id_jhs_pattern_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="support_email",
            field=models.EmailField(blank=True, max_length=254, null=True, verbose_name="Support email"),
        ),
        migrations.AddField(
            model_name="school",
            name="support_phone",
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name="Support phone"),
        ),
    ]
