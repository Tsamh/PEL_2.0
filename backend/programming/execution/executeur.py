"""Point d'entrée : exécuter une `Execution` et enregistrer ses résultats."""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import MESSAGE_INDISPONIBLE, ServiceIndisponible, tronquer
from . import langages
from .comparaison import sorties_egales

logger = logging.getLogger('programming.execution')

MESSAGE_LANGAGE = "Ce langage n'est pas pris en charge par le service d'exécution."


def obtenir_executeur():
    nom = getattr(settings, 'PEL_EXECUTEUR', 'docker')
    if nom == 'factice':
        from .factice import ExecuteurFactice
        return ExecuteurFactice()
    if nom == 'docker':
        from .docker import ExecuteurDocker
        return ExecuteurDocker()
    raise ServiceIndisponible(f"Exécuteur inconnu : {nom}")


def statut_du_resultat(compilation_ok, brut, attendue):
    """Statut d'un test : CE, SE, TLE, MLE, RE, WA ou OK.

    `attendue` est None pour un essai libre (`essai_run`) : OK si le programme se termine normalement.
    """
    from programming.models import ResultatTest
    if not compilation_ok:
        return ResultatTest.CE
    if brut is None or brut.get('erreur_service'):
        return ResultatTest.SE
    if brut.get('delai_depasse'):
        return ResultatTest.TLE
    if brut.get('memoire_depassee'):
        return ResultatTest.MLE
    if brut.get('code_sortie') != 0:
        return ResultatTest.RE
    if attendue is None:
        return ResultatTest.OK
    return ResultatTest.OK if sorties_egales(brut.get('sortie') or '', attendue) else ResultatTest.WA


def _cas(execution):
    """[(CasDeTest ou None, entrée, sortie attendue ou None)] selon le type d'exécution."""
    from programming.models import Execution
    if execution.type == Execution.ESSAI_RUN:
        return [(None, execution.entree or '', None)]
    tests = execution.exercice.tests.order_by('ordre', 'id')
    if execution.type == Execution.ESSAI_TEST:
        tests = tests.filter(public=True)
    return [(cas, cas.entree, cas.sortie_attendue) for cas in tests]


def _fichiers(execution):
    from programming.models import Execution
    if execution.type == Execution.CORRECTION and execution.reponse_id:
        fichiers = execution.reponse.fichiers
    else:
        fichiers = execution.fichiers
    return fichiers if isinstance(fichiers, list) else []


def _public(cas):
    """Un essai libre (sans CasDeTest) est assimilé à un test public."""
    return cas is None or bool(cas.public)


def _remettre_en_ordre(rapport, ordre_execution, nombre):
    """Remet les résultats bruts (reçus dans l'ordre d'exécution) dans l'ordre des cas."""
    bruts = rapport.get('resultats') or []
    remis = [None] * nombre
    for position, indice in enumerate(ordre_execution):
        if position < len(bruts):
            remis[indice] = bruts[position]
    return {**rapport, 'resultats': remis}


def _terminer(execution, statut, message='', compilation='', resultats=()):
    """Enregistre la fin de l'exécution si ce worker détient encore la réclamation.

    `debut`, posé par la réclamation, sert de jeton : la mise à jour est conditionnée à
    (pk, statut = en_cours, debut inchangé). Si l'exécution a été reprise, réclamée par un autre worker ou
    abandonnée entre-temps, rien n'est écrit (ni résultats, ni statut). Renvoie True si la fin est enregistrée.
    """
    from programming.models import Execution, ResultatTest
    with transaction.atomic():
        ecrit = Execution.objects.filter(pk=execution.pk, statut=Execution.EN_COURS, debut=execution.debut).update(
            statut=statut, message=tronquer(message), compilation=tronquer(compilation), fin=timezone.now())
        if not ecrit:
            logger.warning("Réclamation périmée pour l'exécution %s : résultats écartés", execution.pk)
            return False
        execution.resultats.all().delete()
        ResultatTest.objects.bulk_create(resultats)
    execution.refresh_from_db()
    return True


def _terminer_en_erreur(execution, message):
    """Enregistre l'échec ; si l'enregistrement lui-même échoue (base indisponible), l'exception remonte et
    l'exécution, restée en cours, est reprise par la récupération des exécutions bloquées."""
    from programming.models import Execution
    return _terminer(execution, Execution.ERREUR, message=message)


def executer(execution):
    """Exécute `execution` avec l'exécuteur choisi par PEL_EXECUTEUR et enregistre le résultat.

    Statut final `terminee` (avec un ResultatTest par cas) ou `erreur` (avec un message). Ne lève pas
    pour une panne du service ni pour un résultat impossible à enregistrer : l'exécution passe en
    `erreur` avec « Le service d'exécution est indisponible. ». Renvoie True si la fin a été enregistrée, False
    si ce worker n'avait plus la réclamation (résultats écartés).
    """
    from programming.models import Execution
    langage = execution.devoir.langage
    if langage not in langages.LANGAGES:
        return _terminer_en_erreur(execution, MESSAGE_LANGAGE)
    try:
        cas = _cas(execution)
        fichiers = _fichiers(execution)
        exercice = execution.exercice
        probleme = langages.probleme_fichiers(langage, fichiers)
        if probleme:
            rapport = {'compilation_ok': False, 'compilation': probleme, 'resultats': []}
        else:
            # Tests publics d'abord, cachés ensuite : l'état laissé par un test caché (/tmp, IPC) ne peut pas
            # apparaître dans la sortie, visible, d'un test public. Les résultats gardent l'ordre `ordre`.
            ordre_execution = sorted(range(len(cas)), key=lambda i: (not _public(cas[i][0]), i))
            rapport = obtenir_executeur().lancer(langage, fichiers,
                                                 [{'entree': cas[i][1]} for i in ordre_execution],
                                                 exercice.limite_temps_ms, exercice.limite_memoire_mo)
            rapport = _remettre_en_ordre(rapport, ordre_execution, len(cas))
    except ServiceIndisponible as erreur:
        logger.warning("Service d'exécution indisponible pour l'exécution %s : %s", execution.pk, erreur)
        return _terminer_en_erreur(execution, MESSAGE_INDISPONIBLE)
    except Exception:  # noqa: BLE001 : toute panne de l'exécuteur est une erreur du service
        logger.exception("Panne de l'exécuteur pour l'exécution %s", execution.pk)
        return _terminer_en_erreur(execution, MESSAGE_INDISPONIBLE)

    try:
        return _terminer(execution, Execution.TERMINEE, compilation=rapport.get('compilation') or '',
                  resultats=_resultats(execution, cas, rapport))
    except Exception:  # noqa: BLE001 : un résultat impossible à enregistrer ne doit pas laisser l'exécution en cours
        logger.exception("Enregistrement des résultats impossible pour l'exécution %s", execution.pk)
        return _terminer_en_erreur(execution, MESSAGE_INDISPONIBLE)


def _resultats(execution, cas, rapport):
    from programming.models import CasDeTest, ResultatTest
    # Un test remplacé pendant l'exécution (devoir modifié) : son résultat reste, sans citer le test disparu.
    restants = set(CasDeTest.objects.filter(pk__in=[objet.pk for objet, _, _ in cas if objet is not None])
                   .values_list('pk', flat=True))
    compilation_ok = bool(rapport.get('compilation_ok'))
    bruts = rapport.get('resultats') or []
    resultats = []
    for ordre, (objet, _, attendue) in enumerate(cas):
        brut = bruts[ordre] if compilation_ok and ordre < len(bruts) else None
        resultats.append(ResultatTest(
            execution=execution, cas=objet if objet is not None and objet.pk in restants else None, ordre=ordre,
            statut=statut_du_resultat(compilation_ok, brut, attendue),
            temps_ms=max(0, int((brut or {}).get('temps_ms') or 0)),
            sortie=tronquer((brut or {}).get('sortie')), erreurs=tronquer((brut or {}).get('erreurs')),
        ))
    return resultats
