"""Note proposée d'une soumission : tests pondérés, tests cachés d'abord."""
from decimal import Decimal, ROUND_HALF_UP

CENTIEMES = Decimal('0.01')


def note_exercice(exercice, resultats):
    """Points obtenus à un exercice, en `Decimal`.

    Ce sont les poids des tests cachés réussis, rapportés à ceux de tous les tests cachés, qui comptent ; les
    tests publics ne servent que si l'exercice n'a aucun test caché. Sans test : 0. Un test sans résultat
    compte comme échoué. `resultats` : les `ResultatTest` d'une correction de l'exercice.
    """
    from programming.models import ResultatTest
    tests = list(exercice.tests.all())
    retenus = [t for t in tests if not t.public] or tests
    total = sum(t.poids for t in retenus)
    if not total:
        return Decimal('0')
    reussis = {r.cas_id for r in resultats if r.statut == ResultatTest.OK and r.cas_id is not None}
    obtenu = sum(t.poids for t in retenus if t.id in reussis)
    return (Decimal(obtenu) / Decimal(total) * exercice.points).quantize(CENTIEMES, rounding=ROUND_HALF_UP)


def derniere_correction(reponse):
    """Dernière exécution de type correction d'une réponse (ou None)."""
    from programming.models import Execution
    return reponse.executions.filter(type=Execution.CORRECTION).order_by('-id').first()


def note_soumission(soumission):
    """Somme, sur les exercices du devoir, de la note de la dernière correction de chaque réponse.

    Un exercice sans réponse ou sans correction terminée vaut 0.
    """
    from programming.models import Execution
    reponses = {r.exercice_id: r for r in soumission.reponses.all()}
    total = Decimal('0')
    for exercice in soumission.devoir.exercices.all():
        reponse = reponses.get(exercice.id)
        correction = derniere_correction(reponse) if reponse else None
        if correction is None or correction.statut != Execution.TERMINEE:
            continue
        total += note_exercice(exercice, list(correction.resultats.all()))
    return total.quantize(CENTIEMES, rounding=ROUND_HALF_UP)
