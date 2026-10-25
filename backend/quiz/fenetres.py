"""Fenêtre effective d'un quiz pour un étudiant : sessions, rattrapages et tentatives supplémentaires.

Sans session applicable, la fenêtre générale du quiz s'applique (comportement d'origine).
"""
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from .models import SessionQuiz


@dataclass
class Fenetre:
    intervalles: list
    tentatives_max: int
    maintenant: datetime
    rattrapage_a_venir: bool = False

    def _contient(self, intervalle):
        debut, fin = intervalle
        return (debut is None or debut <= self.maintenant) and (fin is None or self.maintenant < fin)

    @property
    def ouverte(self):
        """L'intervalle ouvert qui ferme le plus tard (une fermeture nulle l'emporte), ou None."""
        ouverts = [i for i in self.intervalles if self._contient(i)]
        if not ouverts:
            return None
        return max(ouverts, key=lambda i: (i[1] is None, i[1] or self.maintenant))

    @property
    def prochaine_ouverture(self):
        futures = [debut for debut, _ in self.intervalles if debut is not None and debut > self.maintenant]
        return min(futures) if futures else None

    @property
    def terminee(self):
        return self.ouverte is None and self.prochaine_ouverture is None

    def affichee(self):
        """Intervalle à montrer : l'ouvert, sinon le prochain, sinon le dernier fermé."""
        if self.ouverte is not None:
            return self.ouverte
        a_venir = [i for i in self.intervalles if i[0] is not None and i[0] > self.maintenant]
        if a_venir:
            return min(a_venir, key=lambda i: i[0])
        fermes = [i for i in self.intervalles if i[1] is not None]
        return max(fermes, key=lambda i: i[1]) if fermes else (None, None)


def _sessions_applicables(quiz, etudiant):
    par_classe = SessionQuiz.objects.filter(classes__inscriptions__etudiant=etudiant).values('pk')
    par_groupe = SessionQuiz.objects.filter(
        groupes__membres=etudiant, groupes__classe__inscriptions__etudiant=etudiant,
    ).values('pk')
    normales = SessionQuiz.objects.filter(quiz=quiz, type=SessionQuiz.NORMALE).filter(
        Q(pk__in=par_classe) | Q(pk__in=par_groupe)
    )
    rattrapages = SessionQuiz.objects.filter(quiz=quiz, type=SessionQuiz.RATTRAPAGE, etudiants=etudiant)
    return list(normales), list(rattrapages)


def construire(quiz, normales, rattrapages, maintenant):
    """Fenêtre à partir des sessions déjà connues (calcul pur, sans requête)."""
    intervalles = [(s.ouverture, s.fermeture) for s in normales] or [(quiz.date_debut, quiz.date_fin)]
    intervalles += [(s.ouverture, s.fermeture) for s in rattrapages]
    # Les tentatives supplémentaires ne servent que pendant que leur rattrapage est ouvert.
    bonus = sum(s.tentatives_supplementaires for s in rattrapages if s.ouverture <= maintenant < s.fermeture)
    a_venir = any(s.ouverture > maintenant for s in rattrapages)
    return Fenetre(intervalles=intervalles, tentatives_max=quiz.tentatives_autorisees + bonus,
                   maintenant=maintenant, rattrapage_a_venir=a_venir)


def fenetre(quiz, etudiant, maintenant=None):
    normales, rattrapages = _sessions_applicables(quiz, etudiant)
    return construire(quiz, normales, rattrapages, maintenant or timezone.now())
