"""Statistiques des quiz pour l'enseignant : population, notes, questions et suivi individuel.

Les indicateurs portent sur la meilleure tentative soumise de chaque étudiant. Le nombre de
requêtes ne dépend pas du nombre d'étudiants (préchargements).
"""
import statistics
from collections import Counter
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import F, Q

from accounts.permissions import ADMIN, ENSEIGNANT, ETUDIANT, RESPONSABLE, SUPERADMIN
from accounts.scoping import classes_enseignant, q_evaluation_etablissement

from .correction import arrondir
from .models import Quiz, ReponseQuiz, TentativeQuiz
from .passage import meilleure_tentative

ZERO = Decimal('0')
CENT = Decimal('100')
NB_TRANCHES = 10
NB_ERREURS = 5
SOUMIS, EN_COURS, NON_COMMENCE = 'soumis', 'en_cours', 'non_commence'


def _dec(valeur):
    return str(arrondir(valeur))


def _part(nombre, total):
    return _dec(Decimal(nombre) * CENT / total) if total else '0.00'


def _pourcentage(score, maximum):
    return arrondir(score * CENT / maximum) if maximum else ZERO


def _nom(user):
    return user.get_full_name() or user.username


def etudiants_affectes(quiz):
    """Étudiants affectés au quiz : par classe, par groupe (inscrits dans la classe du groupe) ou nominativement."""
    User = get_user_model()
    par_classe = User.objects.filter(inscriptions__classe__quizzes_affectes=quiz).values('pk')
    par_groupe = User.objects.filter(
        groupes__quizzes_affectes=quiz, groupes__classe__inscriptions__etudiant=F('pk'),
    ).values('pk')
    return User.objects.filter(role=ETUDIANT).filter(
        Q(pk__in=par_classe) | Q(pk__in=par_groupe) | Q(pk__in=quiz.etudiants.values('pk'))
    )


def quizzes_du_perimetre(user):
    qs = Quiz.objects.all()
    if user.role == SUPERADMIN:
        return qs
    if user.role in (ADMIN, RESPONSABLE):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id)) if user.etablissement_id else qs.none()
    if user.role == ENSEIGNANT:
        return qs.filter(cree_par=user)
    return qs.none()


def etudiants_du_perimetre(user):
    qs = get_user_model().objects.filter(role=ETUDIANT)
    if user.role == SUPERADMIN:
        return qs
    if user.role in (ADMIN, RESPONSABLE):
        return qs.filter(etablissement_id=user.etablissement_id) if user.etablissement_id else qs.none()
    if user.role == ENSEIGNANT:
        return qs.filter(
            Q(pk__in=qs.filter(inscriptions__classe__in=classes_enseignant(user)).values('pk'))
            | Q(pk__in=qs.filter(tentatives_quiz__quiz__cree_par=user).values('pk'))
        )
    return qs.none()


def _tentatives(quiz, avec_choix=True):
    return list(
        quiz.tentatives.select_related('etudiant')
        .prefetch_related('reponses__choix_selectionnes' if avec_choix else 'reponses').order_by('numero', 'id')
    )


def _contexte(quiz, avec_choix=True):
    """(étudiants concernés {pk: user}, tentatives par étudiant, meilleures tentatives)."""
    tentatives = _tentatives(quiz, avec_choix)
    par_etudiant = {}
    for t in tentatives:
        par_etudiant.setdefault(t.etudiant_id, []).append(t)
    etudiants = {u.pk: u for u in etudiants_affectes(quiz)}
    for t in tentatives:
        etudiants.setdefault(t.etudiant_id, t.etudiant)
    retenues = [m for m in (meilleure_tentative(ts) for ts in par_etudiant.values()) if m is not None]
    return etudiants, par_etudiant, retenues


def _statut(tentatives):
    if any(t.statut == TentativeQuiz.SOUMISE for t in tentatives):
        return SOUMIS
    return EN_COURS if tentatives else NON_COMMENCE


def _population(etudiants, par_etudiant):
    statuts = Counter(_statut(par_etudiant.get(pk, [])) for pk in etudiants)
    return {
        'concernes': len(etudiants), 'soumis': statuts[SOUMIS], 'en_cours': statuts[EN_COURS],
        'non_commences': statuts[NON_COMMENCE], 'taux_participation': _part(statuts[SOUMIS], len(etudiants)),
    }


def _notes(retenues, score_max):
    vide = {'nb': 0, 'score_max': _dec(score_max), 'moyenne': None, 'mediane': None, 'minimum': None, 'maximum': None,
            'ecart_type': None, 'moyenne_pourcentage': None, 'mediane_pourcentage': None, 'provisoires': 0,
            'duree_mediane': None}
    if not retenues:
        return vide
    scores = [t.score for t in retenues]
    pourcentages = [_pourcentage(t.score, t.score_max) for t in retenues]
    durees = [t.duree_secondes for t in retenues if t.duree_secondes is not None]
    return {
        'nb': len(scores), 'score_max': _dec(score_max),
        'moyenne': _dec(sum(scores) / len(scores)), 'mediane': _dec(statistics.median(scores)),
        'minimum': _dec(min(scores)), 'maximum': _dec(max(scores)), 'ecart_type': _dec(statistics.pstdev(scores)),
        'moyenne_pourcentage': _dec(sum(pourcentages) / len(pourcentages)),
        'mediane_pourcentage': _dec(statistics.median(pourcentages)),
        'provisoires': sum(1 for t in retenues if t.est_provisoire),
        'duree_mediane': int(statistics.median(durees)) if durees else None,
    }


def _distribution(retenues):
    tranches = [0] * NB_TRANCHES
    for t in retenues:
        indice = int(_pourcentage(t.score, t.score_max) // 10)
        tranches[min(NB_TRANCHES - 1, max(0, indice))] += 1
    return [{'de': i * 10, 'a': (i + 1) * 10, 'nb': nb} for i, nb in enumerate(tranches)]


def _repondue(question, reponse):
    if reponse is None:
        return False
    if question.type_question == 'courte':
        return bool(reponse.texte_reponse.strip())
    return bool(reponse.choix_selectionnes.all())


def _question(question, reponses):
    """Statistiques d'une question ; `reponses` : une réponse (ou None) par tentative retenue."""
    total = len(reponses)
    repondues = [r for r in reponses if _repondue(question, r)]
    reussies = sum(1 for r in repondues if r.score_obtenu >= question.points)
    scores = [r.score_obtenu if r is not None else ZERO for r in reponses]
    donnees = {
        'id': question.id, 'ordre': question.ordre, 'texte': question.texte, 'type_question': question.type_question,
        'points': _dec(question.points), 'nb_reponses': len(repondues), 'nb_sans_reponse': total - len(repondues),
        'taux_reussite': _part(reussies, total), 'score_moyen': _dec(sum(scores) / total) if total else '0.00',
        'nb_a_valider': sum(1 for r in reponses if r is not None and r.statut_correction == ReponseQuiz.A_VALIDER),
        'choix': [], 'erreurs_frequentes': [],
    }
    if question.type_question == 'courte':
        fausses = Counter(' '.join(r.texte_reponse.lower().split()) for r in repondues
                         if r.score_obtenu < question.points and r.statut_correction != ReponseQuiz.A_VALIDER)
        donnees['erreurs_frequentes'] = [{'texte': t, 'nb': nb} for t, nb in fausses.most_common(NB_ERREURS)]
        return donnees
    coches = Counter(c.id for r in repondues for c in r.choix_selectionnes.all())
    donnees['choix'] = [
        {'id': c.id, 'texte': c.texte, 'est_correct': c.est_correct, 'nb': coches[c.id], 'pourcentage': _part(coches[c.id], total)}
        for c in question.choix.all()
    ]
    fausses = sorted((c for c in donnees['choix'] if not c['est_correct'] and c['nb']), key=lambda c: -c['nb'])
    donnees['erreurs_frequentes'] = [{'texte': c['texte'], 'nb': c['nb']} for c in fausses[:NB_ERREURS]]
    return donnees


def _suivi(etudiants, par_etudiant):
    lignes = []
    for pk, etudiant in etudiants.items():
        tentatives = par_etudiant.get(pk, [])
        soumises = [t for t in tentatives if t.statut == TentativeQuiz.SOUMISE]
        meilleure = meilleure_tentative(tentatives)
        lignes.append({
            'id': pk, 'nom': _nom(etudiant), 'statut': _statut(tentatives), 'nb_tentatives': len(tentatives),
            'meilleure': _dec(meilleure.score) if meilleure else None,
            'derniere': _dec(soumises[-1].score) if soumises else None,
            'score_max': _dec(meilleure.score_max) if meilleure else None,
            'temps_total': sum(t.duree_secondes or 0 for t in soumises),
            'progression': [_dec(t.score) for t in soumises],
            'provisoire': bool(meilleure and meilleure.est_provisoire),
        })
    return sorted(lignes, key=lambda l: l['nom'].lower())


def statistiques_quiz(quiz):
    etudiants, par_etudiant, retenues = _contexte(quiz)
    questions = list(quiz.questions.prefetch_related('choix').order_by('ordre', 'id'))
    index = {t.pk: {r.question_id: r for r in t.reponses.all()} for t in retenues}
    return {
        'titre': quiz.titre,
        'population': _population(etudiants, par_etudiant),
        'notes': _notes(retenues, sum((q.points for q in questions), ZERO)),
        'distribution': _distribution(retenues),
        'questions': [_question(q, [index[t.pk].get(q.id) for t in retenues]) for q in questions],
        'etudiants': _suivi(etudiants, par_etudiant),
    }


def resume_quiz(quiz):
    etudiants, par_etudiant, retenues = _contexte(quiz, avec_choix=False)
    score_max = sum((q.points for q in quiz.questions.all()), ZERO)
    notes = _notes(retenues, score_max)
    a_valider = sum(
        1 for ts in par_etudiant.values() for t in ts if t.statut == TentativeQuiz.SOUMISE
        for r in t.reponses.all() if r.statut_correction == ReponseQuiz.A_VALIDER
    )
    return {
        'id': quiz.id, 'titre': quiz.titre, 'est_publie': quiz.est_publie,
        'population': _population(etudiants, par_etudiant),
        'notes': {cle: notes[cle] for cle in ('nb', 'score_max', 'moyenne', 'mediane', 'moyenne_pourcentage')},
        'nb_a_valider': a_valider,
    }


def resultats_etudiant(etudiant, quizzes):
    """Résultats de l'étudiant sur les quiz donnés, dans l'ordre chronologique."""
    tentatives = list(
        TentativeQuiz.objects.filter(etudiant=etudiant, quiz__in=quizzes)
        .select_related('quiz').prefetch_related('reponses').order_by('numero', 'id')
    )
    par_quiz = {}
    for t in tentatives:
        par_quiz.setdefault(t.quiz_id, []).append(t)
    resultats = []
    for ts in par_quiz.values():
        meilleure = meilleure_tentative(ts)
        reference = meilleure or ts[0]
        date = meilleure.soumise_le if meilleure else reference.debut
        resultats.append({
            'quiz': reference.quiz_id, 'titre': reference.quiz.titre, 'date': date,
            'statut': _statut(ts), 'nb_tentatives': len(ts),
            'score': _dec(meilleure.score) if meilleure else None,
            'score_max': _dec(meilleure.score_max) if meilleure else None,
            'pourcentage': _dec(_pourcentage(meilleure.score, meilleure.score_max)) if meilleure else None,
            'provisoire': bool(meilleure and meilleure.est_provisoire),
        })
    resultats.sort(key=lambda r: r['date'])
    return {'etudiant': {'id': etudiant.pk, 'nom': _nom(etudiant)}, 'resultats': resultats}
