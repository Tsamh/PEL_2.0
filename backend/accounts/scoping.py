from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .permissions import SUPERADMIN, ADMIN, RESPONSABLE, ENSEIGNANT, ETUDIANT

MESSAGE_HORS_PERIMETRE = "Cet élément ne fait pas partie de votre périmètre."


def classes_enseignant(user):
    from referentiel.models import Classe
    return Classe.objects.filter(
        Q(affectations_enseignants__enseignant=user) | Q(enseignants_matieres__enseignant=user)
    ).distinct()


def classes_etudiant(user):
    from referentiel.models import Classe
    return Classe.objects.filter(inscriptions__etudiant=user).distinct()


def classes_du_perimetre(user):
    from referentiel.models import Classe
    if user.role == SUPERADMIN:
        return Classe.objects.all()
    if user.role in (ADMIN, RESPONSABLE):
        if not user.etablissement_id:
            return Classe.objects.none()
        return Classe.objects.filter(filiere__etablissement_id=user.etablissement_id)
    if user.role == ENSEIGNANT:
        return classes_enseignant(user)
    if user.role == ETUDIANT:
        return classes_etudiant(user)
    return Classe.objects.none()


def filieres_etudiant(user):
    return classes_etudiant(user).values_list('filiere_id', flat=True)


def q_filiere_niveau_etudiant(user, prefix=''):
    """Q vrai pour les objets dont (filière, niveau) correspond à une classe de l'étudiant."""
    q = Q(pk__in=[])
    for filiere_id, niveau_id in classes_etudiant(user).values_list('filiere_id', 'niveau_id'):
        q |= Q(**{f'{prefix}filiere_id': filiere_id, f'{prefix}niveau_id': niveau_id})
    return q


def q_evaluation_etablissement(etablissement_id, prefix=''):
    """Quiz ou devoir rattaché à l'établissement par sa filière, ou par son créateur s'il n'a pas de filière."""
    return (
        Q(**{f'{prefix}filiere__etablissement_id': etablissement_id})
        | Q(**{f'{prefix}filiere__isnull': True, f'{prefix}cree_par__etablissement_id': etablissement_id})
    )


def verifier_compte_du_perimetre(acteur, compte, role):
    if compte.role != role:
        raise ValidationError({'detail': "Ce compte n'a pas le rôle attendu."})
    if acteur.role != SUPERADMIN and compte.etablissement_id != acteur.etablissement_id:
        raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})


MAX_ENTIER = 2 ** 63 - 1  # borne des entiers SQLite et PostgreSQL (bigint)


def en_entier(valeur):
    """Entier lu depuis une valeur de requête (int ou chaîne de chiffres ASCII), sinon None.
    Les booléens et les valeurs au-delà de MAX_ENTIER sont refusés (elles feraient échouer la requête SQL)."""
    if isinstance(valeur, bool):
        return None
    if isinstance(valeur, str) and valeur.isascii() and valeur.isdecimal():
        valeur = int(valeur)
    if isinstance(valeur, int) and valeur <= MAX_ENTIER:
        return valeur
    return None


def verifier_filiere_du_perimetre(acteur, filiere):
    if filiere is None or acteur.role == SUPERADMIN:
        return
    if acteur.role == ENSEIGNANT:
        autorisee = classes_enseignant(acteur).filter(filiere_id=filiere.pk).exists()
    else:
        autorisee = bool(acteur.etablissement_id) and filiere.etablissement_id == acteur.etablissement_id
    if not autorisee:
        raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})


def verifier_references_evaluation(acteur, data):
    """Refuse une année, une période ou une matière (EC) hors de l'établissement de l'acteur dans le corps d'une évaluation.

    Le niveau est global : aucun contrôle. Les clés absentes sont tolérées.
    """
    if acteur.role == SUPERADMIN:
        return
    annee = data.get('annee_academique')
    if annee is not None and (not acteur.etablissement_id or annee.etablissement_id != acteur.etablissement_id):
        raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})
    periode = data.get('periode')
    if periode is not None and (
        not acteur.etablissement_id or periode.semestre.annee_academique.etablissement_id != acteur.etablissement_id
    ):
        raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})
    ec = data.get('ec')
    if ec is not None:
        from referentiel.models import EnseignantMatiere
        if not acteur.etablissement_id or ec.ue.filiere.etablissement_id != acteur.etablissement_id:
            raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})
        if acteur.role == ENSEIGNANT and not EnseignantMatiere.objects.filter(enseignant=acteur, ec=ec).exists():
            raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})


class EtablissementScopedMixin:
    """Filtre le queryset selon le rôle et vérifie à l'écriture que l'objet reste dans le périmètre.

    scope_path : chemin ORM vers l'établissement, utilisé pour admin et responsable.
    scope_etablissement_field : FK directe imposée à l'établissement de l'utilisateur (sauf superadmin).
    """

    scope_path = None
    scope_etablissement_field = None

    def get_queryset(self):
        return self.scope_queryset(super().get_queryset(), self.request.user)

    def scope_queryset(self, qs, user):
        if user.role == SUPERADMIN:
            return qs
        if user.role in (ADMIN, RESPONSABLE):
            if not user.etablissement_id:
                return qs.none()
            return self.gestion_scope(qs, user)
        if user.role == ENSEIGNANT:
            return self.enseignant_scope(qs, user)
        if user.role == ETUDIANT:
            return self.etudiant_scope(qs, user)
        return qs.none()

    def gestion_scope(self, qs, user):
        return qs.filter(**{self.scope_path: user.etablissement_id})

    def enseignant_scope(self, qs, user):
        return qs.none()

    def etudiant_scope(self, qs, user):
        return qs.none()

    def _champs_forces(self):
        user = self.request.user
        if self.scope_etablissement_field and user.role != SUPERADMIN:
            return {self.scope_etablissement_field: user.etablissement}
        return {}

    def assert_in_scope(self, instance):
        user = self.request.user
        if user.role == SUPERADMIN:
            return
        model = type(instance)
        if not self.scope_queryset(model.objects.filter(pk=instance.pk), user).exists():
            raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})

    def perform_create(self, serializer, **kwargs):
        with transaction.atomic():
            instance = serializer.save(**self._champs_forces(), **kwargs)
            self.assert_in_scope(instance)
        return instance

    def perform_update(self, serializer, **kwargs):
        with transaction.atomic():
            instance = serializer.save(**self._champs_forces(), **kwargs)
            self.assert_in_scope(instance)
        return instance
