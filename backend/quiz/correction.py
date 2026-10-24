"""Calcul des notes d'un quiz. Aucune dépendance HTTP : utilisé par le passage et la validation."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .models import ReponseQuiz, fuzzy_match

ZERO = Decimal('0')
CENTIEME = Decimal('0.01')


def arrondir(valeur):
    return Decimal(valeur).quantize(CENTIEME, rounding=ROUND_HALF_UP)


def en_decimal(valeur):
    """Décimal lu depuis une valeur de requête, sinon None. Les booléens et les valeurs non finies sont refusés."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float, str, Decimal)):
        return None
    try:
        nombre = Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        return None
    return nombre if nombre.is_finite() else None


def _borner(valeur, maximum):
    return max(ZERO, min(valeur, maximum))


def noter(question, choix_ids, texte):
    """Note d'une réponse : (score, statut_correction, similarite)."""
    choix = list(question.choix.all())
    if question.type_question == 'courte':
        texte = (texte or '').strip()
        if not texte:
            return arrondir(ZERO), ReponseQuiz.AUTO, 0.0
        similarite, concordance = 0.0, False
        for c in choix:
            if c.est_correct and c.texte.strip():
                ok, sim = fuzzy_match(texte, c.texte)
                similarite = max(similarite, sim)
                concordance = concordance or ok
        score = question.points if concordance else ZERO
        return arrondir(score), ReponseQuiz.A_VALIDER, similarite

    coches = set(choix_ids)
    if question.type_question == 'qcm' and question.mode_notation == question.PAR_CHOIX:
        total = sum((c.points for c in choix if c.id in coches), ZERO)
        return arrondir(_borner(total, question.points)), ReponseQuiz.AUTO, 0.0

    bonnes = {c.id for c in choix if c.est_correct}
    if not coches:
        return arrondir(ZERO), ReponseQuiz.AUTO, 0.0
    # Réponse fausse : la pénalité de la question (0 par défaut) est retirée.
    # ZERO - penalite plutôt que -penalite : évite une note « -0.00 » quand la pénalité vaut 0.
    score = question.points if coches == bonnes else ZERO - question.penalite
    return arrondir(score), ReponseQuiz.AUTO, 0.0


def corriger_tentative(tentative):
    """Note toutes les questions du quiz (une réponse vide est créée si besoin) puis met à jour le score."""
    reponses = {r.question_id: r for r in tentative.reponses.prefetch_related('choix_selectionnes')}
    for question in tentative.quiz.questions.prefetch_related('choix'):
        reponse = reponses.get(question.id)
        if reponse is None:
            reponse = ReponseQuiz.objects.create(tentative=tentative, question=question)
        if reponse.statut_correction == ReponseQuiz.VALIDEE:
            continue
        choix_ids = [c.id for c in reponse.choix_selectionnes.all()]
        reponse.score_obtenu, reponse.statut_correction, reponse.similarite = noter(
            question, choix_ids, reponse.texte_reponse,
        )
        reponse.save(update_fields=['score_obtenu', 'statut_correction', 'similarite'])
    recalculer_score(tentative)


def recalculer_score(tentative):
    tentative.score = arrondir(max(ZERO, sum((r.score_obtenu for r in tentative.reponses.all()), ZERO)))
    tentative.score_max = arrondir(sum((q.points for q in tentative.quiz.questions.all()), ZERO))
    tentative.save(update_fields=['score', 'score_max'])
