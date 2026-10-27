"""Exécutions asynchrones : demande d'essai (Run, Test), consultation du résultat, relance des corrections."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response

from accounts.permissions import ADMIN, ENSEIGNANT, ETUDIANT, RESPONSABLE, SUPERADMIN
from accounts.scoping import en_entier, q_evaluation_etablissement
from quiz.exceptions import Conflit
from .execution import file as file_execution
from .execution.executeur import MESSAGE_LANGAGE
from .execution.langages import LANGAGES
from .models import Execution
from .serializers import CONTENU_FICHIER_MAX, contient_non_stockable, execution_donnees, valider_fichiers

MESSAGE_EN_COURS = "Une exécution est déjà en cours."
MESSAGE_TROP = "Trop d'exécutions : patientez une minute."
MESSAGE_MODE = "Le mode doit être « run » ou « test »."
MESSAGE_EXERCICE = "Exercice introuvable dans ce devoir."
LIMITE_PAR_MINUTE = 20
FENETRE_LIMITE_S = 60
ACTIVES = (Execution.EN_ATTENTE, Execution.EN_COURS)
ESSAIS = (Execution.ESSAI_RUN, Execution.ESSAI_TEST)
MODES = {'run': Execution.ESSAI_RUN, 'test': Execution.ESSAI_TEST}


def langage_executable(devoir):
    return devoir.langage in LANGAGES


def verifier_limite(user):
    """429 au-delà de LIMITE_PAR_MINUTE demandes dans la minute (fenêtre fixe, cache Django, clé par utilisateur)."""
    cle = f'pel:executions:{user.pk}'
    cache.add(cle, 0, FENETRE_LIMITE_S)
    try:
        nombre = cache.incr(cle)
    except ValueError:  # clé expirée entre add et incr
        cache.set(cle, 1, FENETRE_LIMITE_S)
        nombre = 1
    if nombre > LIMITE_PAR_MINUTE:
        raise Throttled(detail=MESSAGE_TROP)


def lire_demande(devoir, donnees):
    """Valide `{exercice, fichiers, mode, entree?}` ; renvoie (exercice, type, fichiers, entree). 400 sinon."""
    if not isinstance(donnees, dict):
        raise ValidationError("Le corps de la requête doit être un objet JSON.")
    exercice_id = en_entier(donnees.get('exercice'))
    exercice = devoir.exercices.filter(pk=exercice_id).first() if exercice_id is not None else None
    if exercice is None:
        raise ValidationError({'exercice': [MESSAGE_EXERCICE]})
    mode = donnees.get('mode')
    if not isinstance(mode, str) or mode not in MODES:
        raise ValidationError({'mode': [MESSAGE_MODE]})
    try:
        fichiers = valider_fichiers(donnees.get('fichiers'))
    except ValidationError as erreur:
        raise ValidationError({'fichiers': erreur.detail})
    entree = donnees.get('entree', '')
    if entree is None:
        entree = ''
    if not isinstance(entree, str) or len(entree) > CONTENU_FICHIER_MAX:
        raise ValidationError({'entree': [f"L'entrée doit être un texte d'au plus {CONTENU_FICHIER_MAX} caractères."]})
    if contient_non_stockable(entree):
        raise ValidationError({'entree': ["L'entrée contient un caractère non autorisé (NUL)."]})
    type_execution = MODES[mode]
    return exercice, type_execution, fichiers, entree if type_execution == Execution.ESSAI_RUN else ''


def demander_essai(user, devoir, donnees):
    """Met en file un essai après les contrôles de limite, de langage, de corps et d'unicité. Renvoie l'exécution."""
    verifier_limite(user)
    if not langage_executable(devoir):
        raise ValidationError({'detail': MESSAGE_LANGAGE})
    exercice, type_execution, fichiers, entree = lire_demande(devoir, donnees)
    with transaction.atomic():
        # Verrou sur l'utilisateur (PostgreSQL) : deux demandes simultanées ne passent pas toutes les deux.
        get_user_model().objects.select_for_update().filter(pk=user.pk).first()
        if Execution.objects.filter(demandeur=user, type__in=ESSAIS, statut__in=ACTIVES).exists():
            raise Conflit(MESSAGE_EN_COURS)
        return file_execution.mettre_en_file(type_execution, user, devoir, exercice, fichiers=fichiers, entree=entree)


class ExecutionViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """`GET executions/{id}/` : le demandeur d'un essai, ou un correcteur du devoir (tout).

    L'étudiant ne voit que ses essais, filtrés (tests cachés réduits au statut et au temps) ; les résultats des
    corrections lui parviennent par la soumission, selon la politique du devoir.
    """
    queryset = Execution.objects.select_related('devoir', 'exercice')
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role == SUPERADMIN:
            return qs
        if user.role == ETUDIANT:
            return qs.filter(demandeur=user, type__in=ESSAIS)
        if user.role == ENSEIGNANT:
            return qs.filter(Q(demandeur=user) | Q(devoir__cree_par=user))
        if user.role in (ADMIN, RESPONSABLE) and user.etablissement_id:
            return qs.filter(Q(demandeur=user) | q_evaluation_etablissement(user.etablissement_id, prefix='devoir__'))
        return qs.none()

    def retrieve(self, request, *args, **kwargs):
        execution = self.get_object()
        return Response(execution_donnees(execution, complet=request.user.role != ETUDIANT))
