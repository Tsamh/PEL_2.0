"""Le fichier principal Java s'appelle Main.java (l'exécuteur l'exige) : main.java est renommé.

Seuls les exercices et réponses des devoirs Java sont touchés. Une liste qui contient déjà Main.java est laissée
telle quelle, le contenu n'est jamais modifié. Le retour ne fait rien : on ne sait plus quels noms étaient en minuscules.
"""
from django.db import migrations

ANCIEN, NOUVEAU = 'main.java', 'Main.java'


def _renommer(fichiers):
    """Liste avec main.java renommé, ou None si rien ne change."""
    if not isinstance(fichiers, list):
        return None
    noms = [f.get('nom') for f in fichiers if isinstance(f, dict)]
    if NOUVEAU in noms or ANCIEN not in noms:
        return None
    return [{**f, 'nom': NOUVEAU} if isinstance(f, dict) and f.get('nom') == ANCIEN else f for f in fichiers]


def renommer(apps, schema_editor):
    Exercice = apps.get_model('programming', 'Exercice')
    ReponseExercice = apps.get_model('programming', 'ReponseExercice')
    for exercice in Exercice.objects.filter(devoir__langage='java'):
        champs = {}
        for champ in ('fichiers_initiaux', 'solution'):
            nouveau = _renommer(getattr(exercice, champ))
            if nouveau is not None:
                setattr(exercice, champ, nouveau)
                champs[champ] = nouveau
        if champs:
            exercice.save(update_fields=list(champs))
    for reponse in ReponseExercice.objects.filter(exercice__devoir__langage='java'):
        nouveau = _renommer(reponse.fichiers)
        if nouveau is not None:
            reponse.fichiers = nouveau
            reponse.save(update_fields=['fichiers'])


class Migration(migrations.Migration):

    dependencies = [
        ('programming', '0008_execution'),
    ]

    operations = [
        migrations.RunPython(renommer, migrations.RunPython.noop),
    ]
