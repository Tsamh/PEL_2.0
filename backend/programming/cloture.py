"""Soumission automatique des brouillons à la fermeture d'un devoir (sous-projet 4c).

Appelée par `executer_file` : pour chaque étudiant affecté qui a des brouillons et aucune soumission, dont la fenêtre
est fermée depuis plus de `DELAI_GRACE`, le dernier enregistrement devient sa soumission (`soumission_auto`).
Un devoir sans fermeture, une année archivée, un devoir non publié ou un étudiant plus affecté ne sont jamais clôturés
(brouillons gardés). Un brouillon invalide ne donne pas de soumission : l'erreur est journalisée.
"""
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.services import log as audit_log
from quiz import acces, fenetres
from quiz.views import etablissement_evaluation
from . import versions
from .models import BrouillonExercice, Devoir, SoumissionDevoir
from .serializers import valider_reponses

logger = logging.getLogger('programming')

# Marge après la fermeture : laisse aboutir les enregistrements et envois en cours.
DELAI_GRACE = timedelta(seconds=30)


def fermee_depuis_assez_longtemps(devoir, etudiant, maintenant):
    """Aucune fenêtre ouverte ni à venir, et dernière fermeture dépassée de plus de `DELAI_GRACE`."""
    fenetre = fenetres.fenetre(devoir, etudiant, maintenant)
    if fenetre.ouverte is not None or fenetre.prochaine_ouverture is not None:
        return False
    fermetures = [fin for _, fin in fenetre.intervalles]
    if not fermetures or None in fermetures:
        return False
    return maintenant - max(fermetures) >= DELAI_GRACE


def _brouillons_sans_soumission():
    """Couples (devoir, étudiant) ayant des brouillons et aucune soumission, devoirs publiés d'années non archivées."""
    deja = SoumissionDevoir.objects.filter(devoir=OuterRef('exercice__devoir'), etudiant=OuterRef('etudiant'))
    return (BrouillonExercice.objects.annotate(deja_soumis=Exists(deja))
            .filter(deja_soumis=False, exercice__devoir__est_publie=True)
            .exclude(exercice__devoir__annee_academique__archivee=True)
            .values_list('exercice__devoir_id', 'etudiant_id').distinct())


def _cloturer(devoir_id, etudiant_id, maintenant):
    """Crée la soumission automatique d'un étudiant, ou renvoie None s'il n'y a pas lieu ; tout sous verrou."""
    etudiant = get_user_model().objects.get(pk=etudiant_id)
    with transaction.atomic():
        devoir = Devoir.objects.select_for_update().select_related('annee_academique').filter(pk=devoir_id).first()
        if devoir is None or not devoir.est_publie:
            return None
        if devoir.annee_academique is not None and devoir.annee_academique.archivee:
            return None
        if not Devoir.objects.filter(pk=devoir.pk).filter(acces.q_affecte(Devoir, etudiant)).exists():
            return None
        if SoumissionDevoir.objects.filter(devoir=devoir, etudiant=etudiant).exists():
            return None
        if not fermee_depuis_assez_longtemps(devoir, etudiant, maintenant):
            return None
        brouillons = (BrouillonExercice.objects.filter(etudiant=etudiant, exercice__devoir=devoir)
                      .order_by('exercice__ordre', 'exercice_id'))
        reponses = valider_reponses(
            devoir, [{'exercice': b.exercice_id, 'fichiers': b.fichiers} for b in brouillons] or None)
        soumission = versions.creer_soumission(devoir, etudiant, reponses, auto=True)
    audit_log(None, 'soumission_devoir_auto', cible=soumission, acteur=etudiant,
              etablissement=etablissement_evaluation(devoir),
              details={'type': 'soumission', 'devoir': devoir.pk, 'version': soumission.numero_version})
    return soumission


def cloturer_devoirs_echus(maintenant=None):
    """Soumet les brouillons des devoirs échus ; renvoie le nombre de soumissions créées."""
    maintenant = maintenant or timezone.now()
    creees = 0
    for devoir_id, etudiant_id in list(_brouillons_sans_soumission()):
        try:
            if _cloturer(devoir_id, etudiant_id, maintenant) is not None:
                creees += 1
        except ValidationError as erreur:
            logger.error("Clôture : brouillon invalide, pas de soumission (devoir %s, etudiant %s) : %s",
                         devoir_id, etudiant_id, erreur.detail)
        except Exception:  # noqa: BLE001 : un étudiant en échec ne bloque pas les autres
            logger.exception("Clôture impossible (devoir %s, etudiant %s)", devoir_id, etudiant_id)
    return creees
