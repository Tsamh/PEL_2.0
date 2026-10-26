"""Reprise des devoirs existants : un exercice par devoir, tests publics, réponses, affectation, validation."""
from decimal import Decimal

from django.db import migrations

EXTENSIONS = {'python': 'py', 'javascript': 'js', 'c': 'c', 'cpp': 'cpp', 'java': 'java', 'autre': 'txt'}


def _texte(valeur):
    return '' if valeur is None else str(valeur)


def reprendre(apps, schema_editor):
    Devoir = apps.get_model('programming', 'Devoir')
    Exercice = apps.get_model('programming', 'Exercice')
    CasDeTest = apps.get_model('programming', 'CasDeTest')
    SoumissionDevoir = apps.get_model('programming', 'SoumissionDevoir')
    ReponseExercice = apps.get_model('programming', 'ReponseExercice')
    Classe = apps.get_model('referentiel', 'Classe')

    for devoir in Devoir.objects.all():
        nom = f"main.{EXTENSIONS.get(devoir.langage, 'txt')}"
        exercice = Exercice.objects.create(
            devoir=devoir, ordre=1, titre=devoir.titre, enonce=devoir.description or '',
            fichiers_initiaux=[{'nom': nom, 'contenu': devoir.code_initial or ''}],
            solution=[{'nom': nom, 'contenu': devoir.solution or ''}],
            points=Decimal(devoir.points_max) if devoir.points_max else Decimal('1'),
        )
        cas = devoir.test_cases if isinstance(devoir.test_cases, list) else []
        CasDeTest.objects.bulk_create([
            CasDeTest(exercice=exercice, ordre=i, entree=_texte(c.get('input')),
                      sortie_attendue=_texte(c.get('expected_output')), public=True, poids=1)
            for i, c in enumerate((c for c in cas if isinstance(c, dict)), start=1)
        ])
        ReponseExercice.objects.bulk_create([
            ReponseExercice(soumission=s, exercice=exercice, fichiers=[{'nom': nom, 'contenu': s.code_soumis or ''}])
            for s in SoumissionDevoir.objects.filter(devoir=devoir)
        ])
        if devoir.filiere_id:
            classes = Classe.objects.filter(filiere_id=devoir.filiere_id)
            if devoir.niveau_id:
                classes = classes.filter(niveau_id=devoir.niveau_id)
            if devoir.annee_academique_id:
                classes = classes.filter(annee_academique_id=devoir.annee_academique_id)
            devoir.classes.add(*classes)
        if devoir.est_publie:
            devoir.statut_validation = 'validee'
            devoir.save(update_fields=['statut_validation'])


class Migration(migrations.Migration):

    dependencies = [
        ('programming', '0005_devoirs_exercices'),
    ]

    operations = [
        migrations.RunPython(reprendre, migrations.RunPython.noop),
    ]
