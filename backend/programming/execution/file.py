"""File d'exécution : mise en file, réclamation atomique, reprise des exécutions bloquées, correction."""
import logging
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from . import MESSAGE_INDISPONIBLE
from .docker import DUREE_MAX_S
from .notation import derniere_correction, note_soumission

logger = logging.getLogger('programming.execution')

MAX_REPRISES = 2
# Une exécution peut durer DUREE_MAX_S, plus l'arrêt des conteneurs et le nettoyage : le seuil de reprise
# reste nettement au-dessus (au moins 5 minutes) pour qu'une exécution lente mais saine ne soit jamais relancée.
SEUIL_REPRISE_S = max(300, DUREE_MAX_S + 120)


def mettre_en_file(type, demandeur, devoir, exercice, fichiers=None, entree='', reponse=None):
    """Crée une exécution `en_attente`."""
    from programming.models import Execution
    return Execution.objects.create(type=type, demandeur=demandeur, devoir=devoir, exercice=exercice,
                                    reponse=reponse, fichiers=fichiers or [], entree=entree or '')


def reclamer():
    """Réserve la plus ancienne exécution `en_attente` : la passe `en_cours` avec `debut`.

    Mise à jour conditionnelle (`WHERE statut = 'en_attente'`) dont le nombre de lignes décide : une seule
    réclamation gagne, sur SQLite comme sur PostgreSQL. Renvoie l'exécution ou None.
    """
    from programming.models import Execution
    en_attente = Execution.objects.filter(statut=Execution.EN_ATTENTE).order_by('cree_le', 'id')
    while True:
        if connection.features.has_select_for_update_skip_locked:
            # PostgreSQL : les candidats déjà verrouillés par un autre worker sont ignorés, sans file d'attente.
            with transaction.atomic():
                candidat = en_attente.select_for_update(skip_locked=True).values_list('pk', flat=True).first()
                pris = candidat is not None and Execution.objects.filter(
                    pk=candidat, statut=Execution.EN_ATTENTE).update(
                    statut=Execution.EN_COURS, debut=timezone.now(), fin=None)
        else:
            candidat = en_attente.values_list('pk', flat=True).first()
            pris = candidat is not None and Execution.objects.filter(
                pk=candidat, statut=Execution.EN_ATTENTE).update(
                statut=Execution.EN_COURS, debut=timezone.now(), fin=None)
        if candidat is None:
            return None
        if pris:
            return Execution.objects.select_related('devoir', 'exercice', 'reponse').get(pk=candidat)


def recuperer_bloquees(maintenant=None):
    """Remet en attente les exécutions `en_cours` depuis plus de SEUIL_REPRISE_S (reprises + 1) ; au-delà de
    MAX_REPRISES, les passe en `erreur`. Renvoie (nombre remises en file, nombre abandonnées)."""
    from django.db.models import Q
    from programming.models import Execution
    maintenant = maintenant or timezone.now()
    limite = maintenant - timedelta(seconds=SEUIL_REPRISE_S)
    bloquees = Execution.objects.filter(Q(debut__lt=limite) | Q(debut__isnull=True), statut=Execution.EN_COURS)
    reprises = abandons = 0
    for pk, debut, nombre in list(bloquees.values_list('pk', 'debut', 'reprises')):
        # Conditionnée à l'état lu : une exécution terminée entre-temps n'est pas touchée.
        cible = Execution.objects.filter(pk=pk, statut=Execution.EN_COURS, debut=debut, reprises=nombre)
        if nombre >= MAX_REPRISES:
            if cible.update(statut=Execution.ERREUR, message=MESSAGE_INDISPONIBLE, fin=maintenant):
                abandons += 1
                logger.warning("Exécution %s abandonnée après %s reprises", pk, nombre)
        elif cible.update(statut=Execution.EN_ATTENTE, debut=None, reprises=nombre + 1):
            reprises += 1
            logger.warning("Exécution %s bloquée remise en file (reprise %s)", pk, nombre + 1)
    return reprises, abandons


def corriger_soumission(soumission):
    """Passe la soumission en `en_correction` et met en file une correction par réponse."""
    from programming.models import Execution, SoumissionDevoir
    with transaction.atomic():
        soumission.statut = SoumissionDevoir.EN_CORRECTION
        soumission.save(update_fields=['statut'])
        executions = [
            mettre_en_file(Execution.CORRECTION, soumission.etudiant, soumission.devoir, reponse.exercice,
                           reponse=reponse)
            for reponse in soumission.reponses.select_related('exercice')
        ]
    if not executions:
        _noter(soumission)
    return executions


def _noter(soumission):
    from programming.models import SoumissionDevoir
    note = note_soumission(soumission)
    modifiees = SoumissionDevoir.objects.filter(pk=soumission.pk, statut=SoumissionDevoir.EN_CORRECTION).update(
        note_proposee=note, statut=SoumissionDevoir.CORRIGEE_AUTO)
    if modifiees:
        soumission.note_proposee = note
        soumission.statut = SoumissionDevoir.CORRIGEE_AUTO
    return bool(modifiees)


def apres_correction(execution):
    """Quand les dernières corrections de toutes les réponses sont `terminee`, calcule `note_proposee` et
    passe la soumission `corrigee_auto`. Une correction en erreur la laisse `en_correction`. Renvoie True si
    la soumission vient d'être notée."""
    from programming.models import Execution, SoumissionDevoir
    if execution.type != Execution.CORRECTION or execution.reponse_id is None:
        return False
    with transaction.atomic():
        soumission = (SoumissionDevoir.objects.select_for_update(of=('self',)).select_related('devoir')
                      .get(pk=execution.reponse.soumission_id))
        if soumission.statut != SoumissionDevoir.EN_CORRECTION:
            return False
        for reponse in soumission.reponses.all():
            derniere = derniere_correction(reponse)
            if derniere is None or derniere.statut != Execution.TERMINEE:
                return False
        return _noter(soumission)


def traiter(execution):
    """Exécute une exécution réclamée puis met à jour la soumission ; n'échoue jamais.

    `execution.debut`, posé par `reclamer`, est le jeton de réclamation : si l'exécution a été reprise ou
    abandonnée entre-temps, rien n'est écrit et la soumission n'est pas notée.
    """
    from programming.models import Execution
    from .executeur import executer
    try:
        ecrit = executer(execution)
    except Exception:  # noqa: BLE001 : une exécution défaillante ne doit pas arrêter le worker
        logger.exception("Échec de l'exécution %s", execution.pk)
        try:
            Execution.objects.filter(pk=execution.pk, statut=Execution.EN_COURS, debut=execution.debut).update(
                statut=Execution.ERREUR, message=MESSAGE_INDISPONIBLE, fin=timezone.now())
        except Exception:  # noqa: BLE001 : la reprise des exécutions bloquées s'en chargera
            logger.exception("Impossible d'enregistrer l'erreur de l'exécution %s", execution.pk)
        return
    if not ecrit:
        return
    try:
        apres_correction(execution)
    except Exception:  # noqa: BLE001
        logger.exception("Mise à jour de la soumission impossible après l'exécution %s", execution.pk)
