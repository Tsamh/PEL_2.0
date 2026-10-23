from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def marquer_soumises(apps, schema_editor):
    TentativeQuiz = apps.get_model('quiz', 'TentativeQuiz')
    for tentative in TentativeQuiz.objects.all():
        tentative.soumise_le = tentative.debut
        tentative.fin_prevue = tentative.debut
        tentative.save(update_fields=['soumise_le', 'fin_prevue'])


def copier_choix(apps, schema_editor):
    ReponseQuiz = apps.get_model('quiz', 'ReponseQuiz')
    for reponse in ReponseQuiz.objects.exclude(choix_selectionne=None):
        reponse.choix_selectionnes.add(reponse.choix_selectionne_id)


class Migration(migrations.Migration):

    dependencies = [
        ("quiz", "0002_resultatquiz_reponsequiz"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Quiz : réglages de passage et de publication
        migrations.AddField(
            model_name="quiz", name="tentatives_autorisees",
            field=models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AddField(model_name="quiz", name="reprise_autorisee", field=models.BooleanField(default=True)),
        migrations.AddField(
            model_name="quiz", name="publication_resultats",
            field=models.CharField(choices=[("immediate", "Immédiate"), ("differee", "Différée")], default="immediate", max_length=10),
        ),
        migrations.AddField(model_name="quiz", name="resultats_publies", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="quiz", name="afficher_corrige", field=models.BooleanField(default=False)),
        migrations.AlterField(
            model_name="quiz", name="duree_minutes",
            field=models.PositiveIntegerField(default=30, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        # Questions et choix : points décimaux, notation par choix
        migrations.AlterField(
            model_name="question", name="points",
            field=models.DecimalField(decimal_places=2, default=Decimal("1"), max_digits=6,
                                      validators=[django.core.validators.MinValueValidator(Decimal("0.01"))]),
        ),
        migrations.AddField(
            model_name="question", name="mode_notation",
            field=models.CharField(choices=[("tout_ou_rien", "Tout ou rien"), ("par_choix", "Points par choix")],
                                   default="tout_ou_rien", max_length=12),
        ),
        migrations.AddField(
            model_name="choix", name="points",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=6),
        ),
        # ResultatQuiz devient TentativeQuiz
        migrations.AlterUniqueTogether(name="resultatquiz", unique_together=set()),
        migrations.RenameModel(old_name="ResultatQuiz", new_name="TentativeQuiz"),
        migrations.RenameField(model_name="tentativequiz", old_name="date_passage", new_name="debut"),
        # Le tri historique référence date_passage : le mettre à jour avant toute requête du RunPython
        migrations.AlterModelOptions(
            name="tentativequiz",
            options={"ordering": ["-debut", "-id"], "verbose_name": "Tentative de quiz",
                     "verbose_name_plural": "Tentatives de quiz"},
        ),
        migrations.AlterField(
            model_name="tentativequiz", name="debut",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.RemoveField(model_name="tentativequiz", name="pourcentage"),
        migrations.RemoveField(model_name="tentativequiz", name="duree_secondes"),
        migrations.AlterField(
            model_name="tentativequiz", name="score",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=8),
        ),
        migrations.AlterField(
            model_name="tentativequiz", name="score_max",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=8),
        ),
        migrations.AlterField(
            model_name="tentativequiz", name="quiz",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tentatives", to="quiz.quiz"),
        ),
        migrations.AlterField(
            model_name="tentativequiz", name="etudiant",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tentatives_quiz",
                                    to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(model_name="tentativequiz", name="numero", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(
            model_name="tentativequiz", name="statut",
            field=models.CharField(choices=[("en_cours", "En cours"), ("soumise", "Soumise")], default="soumise", max_length=10),
        ),
        migrations.AlterField(
            model_name="tentativequiz", name="statut",
            field=models.CharField(choices=[("en_cours", "En cours"), ("soumise", "Soumise")], default="en_cours", max_length=10),
        ),
        migrations.AddField(model_name="tentativequiz", name="fin_prevue", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="tentativequiz", name="soumise_le", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="tentativequiz", name="soumission_auto", field=models.BooleanField(default=False)),
        migrations.RunPython(marquer_soumises, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="tentativequiz",
            constraint=models.UniqueConstraint(fields=("quiz", "etudiant", "numero"), name="tentative_unique_par_numero"),
        ),
        # Réponses : rattachées à une tentative, plusieurs choix, statut de correction
        migrations.RenameField(model_name="reponsequiz", old_name="resultat", new_name="tentative"),
        migrations.AddField(
            model_name="reponsequiz", name="choix_selectionnes",
            field=models.ManyToManyField(blank=True, related_name="reponses_quiz", to="quiz.choix"),
        ),
        migrations.RunPython(copier_choix, migrations.RunPython.noop),
        migrations.RemoveField(model_name="reponsequiz", name="choix_selectionne"),
        migrations.RemoveField(model_name="reponsequiz", name="est_correct"),
        migrations.AlterField(
            model_name="reponsequiz", name="score_obtenu",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=6),
        ),
        migrations.AddField(
            model_name="reponsequiz", name="statut_correction",
            field=models.CharField(choices=[("auto", "Correction automatique"), ("a_valider", "À valider"), ("validee", "Validée")],
                                   default="auto", max_length=10),
        ),
        migrations.AddField(
            model_name="reponsequiz", name="corrige_par",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="corrections_quiz", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(model_name="reponsequiz", name="corrige_le", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddConstraint(
            model_name="reponsequiz",
            constraint=models.UniqueConstraint(fields=("tentative", "question"), name="reponse_unique_par_question"),
        ),
    ]
