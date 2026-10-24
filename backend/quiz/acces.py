"""Accès des étudiants aux quiz : affectation (classes, groupes, étudiants) et code d'accès."""
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from accounts.permissions import ETUDIANT, SUPERADMIN
from accounts.scoping import classes_du_perimetre
from referentiel.models import Inscription

from .models import Quiz


def q_quiz_affecte(user):
    """Q vrai pour les quiz affectés à l'étudiant : par une de ses classes, un de ses groupes ou nominativement."""
    return (
        Q(pk__in=Quiz.objects.filter(classes__inscriptions__etudiant=user).values('pk'))
        | Q(pk__in=Quiz.objects.filter(groupes__membres=user).values('pk'))
        | Q(pk__in=Quiz.objects.filter(etudiants=user).values('pk'))
    )


CLES_CIBLES = ('classes', 'groupes', 'etudiants')


def cibles_vides():
    return {cle: set() for cle in CLES_CIBLES}


def cibles(quiz):
    """Identifiants des cibles actuelles du quiz, par type."""
    return {cle: set(getattr(quiz, cle).values_list('pk', flat=True)) for cle in CLES_CIBLES}


def ecart_cibles(avant, apres):
    """Détails d'audit {ajouts, retraits}, ou None si l'affectation ne change pas."""
    ajouts = {cle: sorted(apres[cle] - avant[cle]) for cle in CLES_CIBLES}
    retraits = {cle: sorted(avant[cle] - apres[cle]) for cle in CLES_CIBLES}
    if not any(ajouts.values()) and not any(retraits.values()):
        return None
    return {'ajouts': ajouts, 'retraits': retraits}


def _nom(user):
    return user.get_full_name() or user.username


def verifier_cibles(acteur, quiz, attrs):
    """Refuse (400) toute cible ajoutée hors du périmètre de l'acteur.

    Les cibles déjà affectées ne sont pas recontrôlées : une affectation reste valide
    si l'enseignant perd ensuite la classe.
    """
    actuelles = cibles(quiz) if quiz is not None else cibles_vides()
    nouvelles = {cle: [o for o in attrs.get(cle, []) if o.pk not in actuelles[cle]] for cle in CLES_CIBLES}
    erreurs = {}
    for etudiant in nouvelles['etudiants']:
        if etudiant.role != ETUDIANT:
            erreurs.setdefault('etudiants', []).append(f"{_nom(etudiant)} n'est pas un étudiant.")
    if acteur.role != SUPERADMIN:
        perimetre = set(classes_du_perimetre(acteur).values_list('pk', flat=True))
        for classe in nouvelles['classes']:
            if classe.pk not in perimetre:
                erreurs.setdefault('classes', []).append(f"La classe {classe.code} ne fait pas partie de votre périmètre.")
        for groupe in nouvelles['groupes']:
            if groupe.classe_id not in perimetre:
                erreurs.setdefault('groupes', []).append(f"Le groupe {groupe.code} ne fait pas partie de votre périmètre.")
        etudiants = [e for e in nouvelles['etudiants'] if e.role == ETUDIANT]
        inscrits = set(
            Inscription.objects.filter(etudiant__in=etudiants, classe_id__in=perimetre).values_list('etudiant_id', flat=True)
        )
        for etudiant in etudiants:
            if etudiant.pk not in inscrits:
                erreurs.setdefault('etudiants', []).append(f"L'étudiant {_nom(etudiant)} ne fait pas partie de votre périmètre.")
    if erreurs:
        raise ValidationError(erreurs)
