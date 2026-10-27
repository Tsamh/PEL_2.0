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


def _terminer(execution, statut, message='', compilation='', resultats=()):
    from programming.models import ResultatTest
    with transaction.atomic():
        execution.resultats.all().delete()
        ResultatTest.objects.bulk_create(resultats)
        execution.statut = statut
        execution.message = message
        execution.compilation = tronquer(compilation)
        execution.fin = timezone.now()
        execution.save(update_fields=['statut', 'message', 'compilation', 'fin'])


def executer(execution):
    """Exécute `execution` avec l'exécuteur choisi par PEL_EXECUTEUR et enregistre le résultat.

    Statut final `terminee` (avec un ResultatTest par cas) ou `erreur` (avec un message). Ne lève pas
    pour une panne du service : elle est enregistrée (« Le service d'exécution est indisponible. »).
    """
    from programming.models import Execution, ResultatTest
    langage = execution.devoir.langage
    if langage not in langages.LANGAGES:
        _terminer(execution, Execution.ERREUR, message=MESSAGE_LANGAGE)
        return
    cas = _cas(execution)
    fichiers = _fichiers(execution)
    exercice = execution.exercice
    probleme = langages.probleme_fichiers(langage, fichiers)
    if probleme:
        rapport = {'compilation_ok': False, 'compilation': probleme, 'resultats': []}
    else:
        try:
            rapport = obtenir_executeur().lancer(langage, fichiers, [{'entree': e} for _, e, _ in cas],
                                                 exercice.limite_temps_ms, exercice.limite_memoire_mo)
        except ServiceIndisponible as erreur:
            logger.warning("Service d'exécution indisponible pour l'exécution %s : %s", execution.pk, erreur)
            _terminer(execution, Execution.ERREUR, message=MESSAGE_INDISPONIBLE)
            return
        except Exception:  # noqa: BLE001 : toute panne de l'exécuteur est une erreur du service
            logger.exception("Panne de l'exécuteur pour l'exécution %s", execution.pk)
            _terminer(execution, Execution.ERREUR, message=MESSAGE_INDISPONIBLE)
            return

    compilation_ok = bool(rapport.get('compilation_ok'))
    bruts = rapport.get('resultats') or []
    resultats = []
    for ordre, (objet, _, attendue) in enumerate(cas):
        brut = bruts[ordre] if compilation_ok and ordre < len(bruts) else None
        resultats.append(ResultatTest(
            execution=execution, cas=objet, ordre=ordre,
            statut=statut_du_resultat(compilation_ok, brut, attendue),
            temps_ms=max(0, int((brut or {}).get('temps_ms') or 0)),
            sortie=tronquer((brut or {}).get('sortie')), erreurs=tronquer((brut or {}).get('erreurs')),
        ))
    _terminer(execution, Execution.TERMINEE, compilation=rapport.get('compilation') or '', resultats=resultats)
