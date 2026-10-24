"""Accès des étudiants aux quiz : affectation (classes, groupes, étudiants) et code d'accès."""
import hmac
import secrets

from django.core.cache import cache
from django.db.models import Q
from rest_framework.exceptions import Throttled, ValidationError

from accounts.permissions import ETUDIANT, SUPERADMIN
from accounts.scoping import classes_du_perimetre
from audit.services import log as audit_log
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


ALPHABET_CODE = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
LONGUEUR_CODE = 6
LIMITE_ESSAIS = 10
FENETRE_ESSAIS = 600  # secondes


def generer_code():
    return ''.join(secrets.choice(ALPHABET_CODE) for _ in range(LONGUEUR_CODE))


def _normaliser(valeur):
    if not isinstance(valeur, str):
        return ''
    return ''.join(valeur.split()).upper()


def verifier_code(request, quiz):
    """Lève 400 si le code est absent ou faux, 429 après LIMITE_ESSAIS erreurs en FENETRE_ESSAIS secondes."""
    cle = f'code_acces:{quiz.pk}:{request.user.pk}'
    if cache.get(cle, 0) >= LIMITE_ESSAIS:
        raise Throttled(detail="Trop d'essais, réessayez dans quelques minutes.")
    fourni = _normaliser(request.data.get('code') if isinstance(request.data, dict) else None)
    if not fourni:
        raise ValidationError({'detail': "Ce quiz demande un code d'accès."})
    if hmac.compare_digest(fourni.encode('utf-8', 'replace'), quiz.code_acces.encode('utf-8', 'replace')):
        return
    cache.add(cle, 0, timeout=FENETRE_ESSAIS)
    try:
        essais = cache.incr(cle)
    except ValueError:
        cache.set(cle, 1, FENETRE_ESSAIS)
        essais = 1
    if essais == LIMITE_ESSAIS:
        audit_log(request, 'echec_code_acces', cible=quiz, details={'quiz': quiz.pk})
    raise ValidationError({'detail': "Code d'accès incorrect."})
