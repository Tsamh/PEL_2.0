from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("programming", "0006_reprise_devoirs"),
    ]

    operations = [
        # Défaut vide : au retour, la colonne est recréée sur des soumissions existantes, puis remplie par 0006.
        migrations.AlterField(
            model_name="soumissiondevoir",
            name="code_soumis",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RemoveField(
            model_name="devoir",
            name="code_initial",
        ),
        migrations.RemoveField(
            model_name="devoir",
            name="description",
        ),
        migrations.RemoveField(
            model_name="devoir",
            name="points_max",
        ),
        migrations.RemoveField(
            model_name="devoir",
            name="solution",
        ),
        migrations.RemoveField(
            model_name="devoir",
            name="test_cases",
        ),
        migrations.RemoveField(
            model_name="soumissiondevoir",
            name="code_soumis",
        ),
    ]
