"""Resoumissions : archivage de la version en cours, remise à zéro, historique des versions."""
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from quiz import fenetres
from quiz.exceptions import Conflit
from .execution import file as file_execution
from .models import Execution, ReponseExercice, SoumissionDevoir, VersionSoumission
from .views_execution import ACTIVES, langage_executable

MESSAGE_CORRECTION_EN_COURS = "Une correction est en cours : réessayez à la fin."
MESSAGE_EXERCICE_MANQUANT = "Un exercice déjà répondu doit figurer dans la nouvelle version : ajoutez-le."


def correction_active(soumission):
    return Execution.objects.filter(reponse__soumission=soumission, type=Execution.CORRECTION,
                                    statut__in=ACTIVES).exists()


def verifier_resoumission(soumission):
    """409 si la soumission ne peut pas être remplacée : option désactivée, note validée, correction active."""
    from .views import MESSAGE_DEJA_SOUMIS, MESSAGE_NOTE_VALIDEE
    if not soumission.devoir.resoumission_autorisee:
        raise Conflit(MESSAGE_DEJA_SOUMIS)
    if soumission.statut == SoumissionDevoir.CORRIGE:
        raise Conflit(MESSAGE_NOTE_VALIDEE)
    if correction_active(soumission):
        raise Conflit(MESSAGE_CORRECTION_EN_COURS)


def resoumission_possible(soumission):
    """Option active, fenêtre ouverte, année non archivée, note non validée, aucune correction active."""
    devoir = soumission.devoir
    if not devoir.resoumission_autorisee or soumission.statut == SoumissionDevoir.CORRIGE:
        return False
    annee = devoir.annee_academique
    if annee is not None and annee.archivee:
        return False
    if fenetres.fenetre(devoir, soumission.etudiant).ouverte is None:
        return False
    return not correction_active(soumission)


def archiver(soumission):
    """Copie la version en cours dans `VersionSoumission` ; à appeler soumission verrouillée."""
    from .execution.notation import derniere_correction
    reponses = []
    for reponse in soumission.reponses.all():
        derniere = derniere_correction(reponse)
        reponses.append({'exercice': reponse.exercice_id, 'fichiers': reponse.fichiers,
                         'correction': derniere.pk if derniere is not None else None})
    return VersionSoumission.objects.create(
        soumission=soumission, numero=soumission.numero_version, date_soumission=soumission.date_soumission,
        soumission_auto=soumission.soumission_auto, note_proposee=soumission.note_proposee, reponses=reponses)


def resoumettre(soumission, reponses):
    """Remplace la version en cours (soumission verrouillée, `reponses` de `valider_reponses`).

    L'appelant a déjà appelé `verifier_resoumission` sous verrou. 400 si un exercice déjà répondu manque. Archive la version, remet la note et le
    commentaire à zéro, met à jour les réponses et met les corrections en file.
    """
    existantes = {r.exercice_id: r for r in soumission.reponses.all()}
    if not set(existantes) <= {exercice.pk for exercice, _ in reponses}:
        raise ValidationError({'reponses': [MESSAGE_EXERCICE_MANQUANT]})
    archiver(soumission)
    soumission.numero_version += 1
    soumission.date_soumission = timezone.now()
    soumission.soumission_auto = False
    soumission.note_proposee = None
    soumission.score = None
    soumission.commentaire = ''
    soumission.statut = SoumissionDevoir.SOUMIS
    soumission.save(update_fields=['numero_version', 'date_soumission', 'soumission_auto', 'note_proposee', 'score',
                                   'commentaire', 'statut'])
    for exercice, fichiers in reponses:
        reponse = existantes.get(exercice.pk)
        if reponse is None:
            ReponseExercice.objects.create(soumission=soumission, exercice=exercice, fichiers=fichiers)
        else:
            reponse.fichiers = fichiers
            reponse.save(update_fields=['fichiers'])
    if langage_executable(soumission.devoir):
        file_execution.corriger_soumission(soumission)


def donnees_version(version, complet, resultats_visibles):
    """Version archivée vue par un correcteur (`complet`) ou un étudiant ; note et résultats si `resultats_visibles`.

    Une exécution supprimée depuis l'archivage est ignorée (correction nulle).
    """
    from .serializers import execution_donnees, fichiers_affichables
    montrer = complet or resultats_visibles
    titres = {e.pk: e.titre for e in version.soumission.devoir.exercices.all()}
    identifiants = [r.get('correction') for r in version.reponses if isinstance(r, dict) and r.get('correction')]
    executions = Execution.objects.in_bulk(identifiants) if montrer else {}
    reponses = []
    for r in version.reponses:
        if not isinstance(r, dict):
            continue
        execution = executions.get(r.get('correction'))
        reponses.append({
            'exercice': r.get('exercice'), 'exercice_titre': titres.get(r.get('exercice'), ''),
            'fichiers': fichiers_affichables(r.get('fichiers')),
            'correction': execution_donnees(execution, complet) if execution is not None else None,
        })
    note = version.note_proposee
    return {
        'numero': version.numero, 'date_soumission': version.date_soumission,
        'soumission_auto': version.soumission_auto,
        'note_proposee': str(note) if montrer and note is not None else None,
        'reponses': reponses,
    }
