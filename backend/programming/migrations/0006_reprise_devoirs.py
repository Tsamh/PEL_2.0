"""Reprise des devoirs existants : un exercice par devoir, tests publics, réponses, affectation, validation.

Le retour reconstruit les anciens champs depuis le premier exercice et la réponse qui le concerne.
"""
from decimal import Decimal

from django.db import migrations
from django.db.models import Max

POINTS_MAX = Decimal('9999.99')  # Exercice.points : max_digits=6, decimal_places=2.
ENTIER_MAX = 2147483647  # Devoir.points_max : PositiveIntegerField.
EXTENSIONS = {'python': 'py', 'javascript': 'js', 'c': 'c', 'cpp': 'cpp', 'java': 'java', 'autre': 'txt'}


def _texte(valeur):
    return '' if valeur is None else str(valeur)


def _points(devoir, SoumissionDevoir):
    """Points de l'exercice repris : l'ancien barème, borné ; sans barème, la meilleure note déjà attribuée."""
    if devoir.points_max:
        return min(Decimal(devoir.points_max), POINTS_MAX)
    meilleur = SoumissionDevoir.objects.filter(devoir=devoir).aggregate(m=Max('score'))['m']
    return min(Decimal(max(meilleur or 0, 1)), POINTS_MAX)


def reprendre(apps, schema_editor):
    Devoir = apps.get_model('programming', 'Devoir')
    Exercice = apps.get_model('programming', 'Exercice')
    CasDeTest = apps.get_model('programming', 'CasDeTest')
    SoumissionDevoir = apps.get_model('programming', 'SoumissionDevoir')
    ReponseExercice = apps.get_model('programming', 'ReponseExercice')
    Classe = apps.get_model('referentiel', 'Classe')
    Inscription = apps.get_model('referentiel', 'Inscription')

    for devoir in Devoir.objects.all():
        nom = f"main.{EXTENSIONS.get(devoir.langage, 'txt')}"
        exercice = Exercice.objects.create(
            devoir=devoir, ordre=1, titre=devoir.titre, enonce=devoir.description or '',
            fichiers_initiaux=[{'nom': nom, 'contenu': devoir.code_initial or ''}],
            solution=[{'nom': nom, 'contenu': devoir.solution or ''}],
            points=_points(devoir, SoumissionDevoir),
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
        # Un étudiant qui a déjà soumis garde l'accès au devoir, même hors des classes retenues.
        couverts = Inscription.objects.filter(classe__in=devoir.classes.all()).values('etudiant_id')
        soumissionnaires = (SoumissionDevoir.objects.filter(devoir=devoir).exclude(etudiant_id__in=couverts)
                            .values_list('etudiant_id', flat=True))
        devoir.etudiants.add(*soumissionnaires)
        if devoir.est_publie:
            devoir.statut_validation = 'validee'
            devoir.save(update_fields=['statut_validation'])


def _premier_contenu(fichiers):
    if isinstance(fichiers, list) and fichiers and isinstance(fichiers[0], dict):
        return _texte(fichiers[0].get('contenu'))
    return ''


def restaurer(apps, schema_editor):
    Devoir = apps.get_model('programming', 'Devoir')
    SoumissionDevoir = apps.get_model('programming', 'SoumissionDevoir')
    ReponseExercice = apps.get_model('programming', 'ReponseExercice')

    for devoir in Devoir.objects.all():
        exercices = list(devoir.exercices.order_by('ordre', 'id'))
        premier = exercices[0] if exercices else None
        bareme = sum((e.points for e in exercices), Decimal('0'))
        devoir.description = premier.enonce if premier else ''
        devoir.code_initial = _premier_contenu(premier.fichiers_initiaux) if premier else ''
        devoir.solution = _premier_contenu(premier.solution) if premier else ''
        devoir.test_cases = [
            {'input': t.entree, 'expected_output': t.sortie_attendue}
            for t in premier.tests.filter(public=True).order_by('ordre', 'id')
        ] if premier else []
        devoir.points_max = min(max(int(bareme), 1), ENTIER_MAX) if exercices else 20
        devoir.save(update_fields=['description', 'code_initial', 'solution', 'test_cases', 'points_max'])
        for soumission in SoumissionDevoir.objects.filter(devoir=devoir):
            reponse = ReponseExercice.objects.filter(soumission=soumission, exercice=premier).first() if premier else None
            soumission.code_soumis = _premier_contenu(reponse.fichiers) if reponse else ''
            soumission.save(update_fields=['code_soumis'])


class Migration(migrations.Migration):

    dependencies = [
        ('programming', '0005_devoirs_exercices'),
    ]

    operations = [
        migrations.RunPython(reprendre, restaurer),
    ]
