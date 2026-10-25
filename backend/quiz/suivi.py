"""Suivi global des quiz : statut, absence et retard de chaque étudiant concerné, puis synthèses.

Les données sont chargées par lots : le nombre de requêtes ne dépend ni du nombre d'étudiants ni du
nombre de quiz. Un étudiant est absent quand sa fenêtre effective est terminée sans tentative soumise.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from accounts.permissions import ETUDIANT
from accounts.scoping import en_entier
from referentiel.models import Classe, Inscription

from . import fenetres, passage
from .models import Quiz, SessionQuiz, TentativeQuiz
from .statistiques import _dec, _nom, _part, _pourcentage, quizzes_du_perimetre

SOUMIS, EN_COURS, ABSENT, A_VENIR = 'soumis', 'en_cours', 'absent', 'a_venir'
DELAI_PAR_DEFAUT = 15

FILTRES = {
    'annee': 'annee_academique_id', 'semestre': 'periode__semestre_id', 'periode': 'periode_id',
    'filiere': 'filiere_id', 'niveau': 'niveau_id', 'ue': 'ec__ue_id', 'ec': 'ec_id',
}


@dataclass
class Ligne:
    quiz: Quiz
    etudiant: object
    statut: str
    retard: int | None
    pourcentage: Decimal | None
    classes: list


@dataclass
class Contexte:
    lignes: list
    classes: dict


def quizzes_suivis(user, params):
    """Quiz du périmètre publiés ou ayant des tentatives, filtrés ; un filtre invalide est ignoré."""
    qs = quizzes_du_perimetre(user).filter(
        Q(est_publie=True) | Q(pk__in=TentativeQuiz.objects.values('quiz_id'))
    )
    for cle, champ in FILTRES.items():
        valeur = en_entier(params.get(cle))
        if valeur is not None:
            qs = qs.filter(**{champ: valeur})
    classe = en_entier(params.get('classe'))
    if classe is not None:
        qs = qs.filter(
            Q(pk__in=Quiz.objects.filter(classes=classe).values('pk'))
            | Q(pk__in=Quiz.objects.filter(groupes__classe=classe).values('pk'))
        )
    return qs.select_related(
        'filiere__etablissement', 'cree_par__etablissement', 'niveau', 'annee_academique', 'periode', 'ec__ue',
    ).prefetch_related('classes', 'groupes__membres', 'etudiants').order_by('titre', 'id')


def _delai(quiz):
    etablissement = quiz.etablissement
    return etablissement.delai_retard_minutes if etablissement is not None else DELAI_PAR_DEFAUT


def _retard(tentatives, fenetre, delai):
    """Minutes de retard de la première tentative au-delà du délai, sinon None."""
    if not tentatives:
        return None
    debut = min(t.debut for t in tentatives)
    ouvertures = [o for o, f in fenetre.intervalles
                  if o is not None and o <= debut and (f is None or debut < f)]
    if not ouvertures:
        return None
    minutes = int((debut - max(ouvertures)).total_seconds() // 60)
    return minutes if minutes > delai else None


def _statut(tentatives, fenetre):
    if any(t.statut == TentativeQuiz.SOUMISE for t in tentatives):
        return SOUMIS
    if tentatives:
        return EN_COURS
    return ABSENT if fenetre.terminee else A_VENIR


class _Session:
    """Session et ses cibles sous forme d'ensembles d'identifiants."""

    def __init__(self, session):
        self.session = session
        self.classes = {c.pk for c in session.classes.all()}
        self.groupes = [(g.classe_id, {m.pk for m in g.membres.all()}) for g in session.groupes.all()]
        self.etudiants = {u.pk for u in session.etudiants.all()}

    def vise(self, etudiant_id, classes_etudiant):
        if self.session.type == SessionQuiz.RATTRAPAGE:
            return etudiant_id in self.etudiants
        return bool(self.classes & classes_etudiant) or any(
            classe in classes_etudiant and etudiant_id in membres for classe, membres in self.groupes
        )


def charger(quizzes, classe=None, maintenant=None):
    """Lignes (quiz, étudiant concerné) ; avec `classe`, seuls les inscrits de cette classe."""
    maintenant = maintenant or timezone.now()
    quizzes = list(quizzes)
    ids = [q.pk for q in quizzes]
    passage.cloturer_expirees(TentativeQuiz.objects.filter(quiz_id__in=ids))

    sessions = {}
    for s in SessionQuiz.objects.filter(quiz_id__in=ids).prefetch_related('classes', 'groupes__membres', 'etudiants'):
        sessions.setdefault(s.quiz_id, []).append(_Session(s))

    classes_visees = {classe} if classe is not None else set()
    for q in quizzes:
        classes_visees |= {c.pk for c in q.classes.all()} | {g.classe_id for g in q.groupes.all()}
    for liste in sessions.values():
        for s in liste:
            classes_visees |= s.classes | {c for c, _ in s.groupes}
    inscrits, classes_de = {}, {}
    for etudiant_id, classe_id in Inscription.objects.filter(classe_id__in=classes_visees).values_list('etudiant_id', 'classe_id'):
        inscrits.setdefault(classe_id, set()).add(etudiant_id)
        classes_de.setdefault(etudiant_id, set()).add(classe_id)

    tentatives = {}
    for t in TentativeQuiz.objects.filter(quiz_id__in=ids).order_by('numero', 'id'):
        tentatives.setdefault((t.quiz_id, t.etudiant_id), []).append(t)

    concernes = {}
    for q in quizzes:
        affectes = {u.pk for u in q.etudiants.all()}
        for c in q.classes.all():
            affectes |= inscrits.get(c.pk, set())
        for g in q.groupes.all():
            affectes |= {m.pk for m in g.membres.all()} & inscrits.get(g.classe_id, set())
        avec_tentative = {e for (quiz_id, e) in tentatives if quiz_id == q.pk}
        concernes[q.pk] = (affectes, avec_tentative)

    tous = set().union(*(a | t for a, t in concernes.values())) if concernes else set()
    etudiants = {u.pk: u for u in get_user_model().objects.filter(pk__in=tous)}
    lignes = []
    for q in quizzes:
        affectes, avec_tentative = concernes[q.pk]
        ids_etudiants = {e for e in affectes if e in etudiants and etudiants[e].role == ETUDIANT} | avec_tentative
        if classe is not None:
            ids_etudiants &= inscrits.get(classe, set())
        classes_quiz = {c.pk for c in q.classes.all()} | {g.classe_id for g in q.groupes.all()}
        delai = _delai(q)
        for e in ids_etudiants:
            if e not in etudiants:
                continue
            classes_etudiant = classes_de.get(e, set())
            applicables = [s.session for s in sessions.get(q.pk, []) if s.vise(e, classes_etudiant)]
            fenetre = fenetres.construire(
                q, [s for s in applicables if s.type == SessionQuiz.NORMALE],
                [s for s in applicables if s.type == SessionQuiz.RATTRAPAGE], maintenant,
            )
            ts = tentatives.get((q.pk, e), [])
            meilleure = passage.meilleure_tentative(ts)
            lignes.append(Ligne(
                quiz=q, etudiant=etudiants[e], statut=_statut(ts, fenetre), retard=_retard(ts, fenetre, delai),
                pourcentage=_pourcentage(meilleure.score, meilleure.score_max) if meilleure else None,
                classes=sorted(classes_quiz & classes_etudiant),
            ))
    return Contexte(lignes=lignes, classes={c.pk: c for c in Classe.objects.filter(pk__in=classes_visees)})


REGROUPEMENTS = ('classe', 'filiere', 'ue', 'ec', 'cohorte')
AUCUN = 'aucun'
SANS = {'classe': 'Sans classe', 'filiere': 'Sans filière', 'ue': 'Sans UE', 'ec': 'Sans matière',
        'cohorte': 'Cohorte non renseignée'}


def _cles(ligne, regroupement, classes):
    """Couples (clé, libellé) des groupes de la ligne ; une ligne peut compter dans plusieurs classes."""
    q = ligne.quiz
    if regroupement == 'classe':
        return [(str(c), classes[c].libelle) for c in ligne.classes if c in classes] or [(AUCUN, SANS['classe'])]
    if regroupement == 'filiere':
        return [(str(q.filiere_id), q.filiere.libelle)] if q.filiere_id else [(AUCUN, SANS['filiere'])]
    if regroupement == 'ue':
        return [(str(q.ec.ue_id), q.ec.ue.libelle)] if q.ec_id else [(AUCUN, SANS['ue'])]
    if regroupement == 'ec':
        return [(str(q.ec_id), q.ec.libelle)] if q.ec_id else [(AUCUN, SANS['ec'])]
    if q.annee_academique_id and q.filiere_id and q.niveau_id:
        return [(f'{q.annee_academique_id}-{q.filiere_id}-{q.niveau_id}',
                 f'{q.annee_academique.libelle} / {q.filiere.libelle} / {q.niveau.libelle}')]
    return [(AUCUN, SANS['cohorte'])]


def _indicateurs(lignes):
    soumis = [l for l in lignes if l.statut == SOUMIS]
    absents = sum(1 for l in lignes if l.statut == ABSENT)
    pourcentages = [l.pourcentage for l in soumis if l.pourcentage is not None]
    return {
        'nb_evaluations': len({l.quiz.pk for l in lignes}), 'concernes': len(lignes), 'soumis': len(soumis),
        'absents': absents, 'retards': sum(1 for l in lignes if l.retard is not None),
        'en_attente': sum(1 for l in lignes if l.statut in (EN_COURS, A_VENIR)),
        'taux_participation': _part(len(soumis), len(soumis) + absents),
        'moyenne_pourcentage': _dec(sum(pourcentages) / len(pourcentages)) if pourcentages else None,
    }


def _groupes(contexte, regroupement):
    groupes = {}
    for ligne in contexte.lignes:
        for cle, libelle in _cles(ligne, regroupement, contexte.classes):
            groupes.setdefault(cle, (libelle, []))[1].append(ligne)
    return groupes


def synthese(contexte, regroupement):
    groupes = [{'cle': cle, 'libelle': libelle, **_indicateurs(lignes)}
               for cle, (libelle, lignes) in _groupes(contexte, regroupement).items()]
    groupes.sort(key=lambda g: (g['cle'] == AUCUN, g['libelle'].lower()))
    return {'regroupement': regroupement, 'groupes': groupes, 'total': _indicateurs(contexte.lignes)}


def evaluations(contexte, regroupement, groupe=None):
    lignes = contexte.lignes
    if groupe:
        lignes = _groupes(contexte, regroupement).get(groupe, ('', []))[1]
    par_quiz = {}
    for ligne in lignes:
        par_quiz.setdefault(ligne.quiz.pk, []).append(ligne)
    resultat = [{
        'quiz': ls[0].quiz.pk, 'titre': ls[0].quiz.titre,
        'periode_libelle': ls[0].quiz.periode.libelle if ls[0].quiz.periode_id else None,
        'ec_libelle': ls[0].quiz.ec.libelle if ls[0].quiz.ec_id else None,
        **_indicateurs(ls),
    } for ls in par_quiz.values()]
    return sorted(resultat, key=lambda e: (e['titre'].lower(), e['quiz']))


def absences(contexte, quiz):
    lignes = [l for l in contexte.lignes if l.quiz.pk == quiz.pk]

    def personne(ligne):
        return {'id': ligne.etudiant.pk, 'nom': _nom(ligne.etudiant),
                'classes': [contexte.classes[c].code for c in ligne.classes if c in contexte.classes]}

    def tri(liste):
        return sorted(liste, key=lambda p: (p['nom'].lower(), p['id']))

    return {
        'quiz': quiz.pk, 'titre': quiz.titre, 'delai_retard_minutes': _delai(quiz),
        'absents': tri([personne(l) for l in lignes if l.statut == ABSENT]),
        'retards': tri([{**personne(l), 'minutes': l.retard} for l in lignes if l.retard is not None]),
    }
