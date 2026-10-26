"""Archivage annuel : une année archivée et tout ce qui en dépend passent en lecture seule et sortent des listes.

Les vues concernées ajoutent `ArchiveMixin` avant `EtablissementScopedMixin` et donnent `annee_path`, le chemin
ORM vers l'année (vide pour l'année elle-même). Un objet sans année n'est jamais concerné.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from audit.services import log as audit_log

MESSAGE_ARCHIVEE = "L'année académique {libelle} est archivée : ses données sont en lecture seule."


class ConflitArchive(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Action impossible : année académique archivée."
    default_code = 'annee_archivee'


def annee_de(objet, chemin):
    """Année de l'objet en suivant `chemin` (« a__b ») ; l'objet lui-même si le chemin est vide."""
    for attribut in filter(None, chemin.split('__')):
        objet = getattr(objet, attribut, None)
        if objet is None:
            return None
    return objet


def verifier_non_archivee(annee):
    if annee is not None and annee.archivee:
        raise ConflitArchive(MESSAGE_ARCHIVEE.format(libelle=annee.libelle))


def verifier_suppression(donnees_archivees, nom):
    """Refuse la suppression d'un élément du référentiel dont la cascade emporterait des données archivées."""
    if any(qs.exists() for qs in donnees_archivees):
        raise ConflitArchive(f"Cette {nom} porte des données d'une année archivée : elle ne peut pas être supprimée.")


def filtrer_archives(qs, chemin, params):
    """Sans `archives=1`, exclut les objets d'une année archivée ; avec, ne garde qu'eux."""
    champ = f'{chemin}__archivee' if chemin else 'archivee'
    if params.get('archives') == '1':
        return qs.filter(**{champ: True})
    return qs.exclude(**{champ: True})


class ArchiveMixin:
    annee_path = ''
    actions_masquees = ('list',)
    parent_params = ()  # paramètres désignant un parent (« quiz », « devoir ») : la liste n'est alors pas masquée

    def _parent_designe(self):
        params = self.request.query_params
        return any(str(params.get(nom, '')).isdigit() for nom in self.parent_params)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in self.actions_masquees and not self._parent_designe():
            qs = filtrer_archives(qs, self.annee_path, self.request.query_params)
        return qs

    def verifier_ecriture(self, objet):
        verifier_non_archivee(annee_de(objet, self.annee_path))

    def update(self, request, *args, **kwargs):
        self.verifier_ecriture(self.get_object())
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.verifier_ecriture(self.get_object())
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer, **kwargs):
        with transaction.atomic():
            instance = super().perform_create(serializer, **kwargs)
            self.verifier_ecriture(instance)
        return instance

    def perform_update(self, serializer, **kwargs):
        with transaction.atomic():
            instance = super().perform_update(serializer, **kwargs)
            self.verifier_ecriture(instance)
        return instance


def archiver(annee, request):
    from quiz.models import TentativeQuiz
    from quiz.passage import cloturer_expirees

    with transaction.atomic():
        type(annee).objects.select_for_update().get(pk=annee.pk)
        annee.refresh_from_db()
        if annee.archivee:
            raise ConflitArchive("Cette année académique est déjà archivée.")
        if annee.date_fin >= timezone.localdate():
            raise ConflitArchive("L'année académique n'est pas terminée : elle ne peut pas encore être archivée.")
        tentatives = TentativeQuiz.objects.filter(quiz__annee_academique=annee)
        cloturer_expirees(tentatives)
        if tentatives.filter(statut=TentativeQuiz.EN_COURS).exists():
            raise ConflitArchive("Des tentatives de quiz sont encore en cours pour cette année.")
        annee.archivee, annee.archivee_le, annee.archivee_par, annee.est_active = (
            True, timezone.now(), request.user, False)
        annee.save(update_fields=['archivee', 'archivee_le', 'archivee_par', 'est_active'])
        audit_log(request, 'archivage_annee', cible=annee, etablissement=annee.etablissement,
                  details={'libelle': annee.libelle})


def desarchiver(annee, request):
    if not annee.archivee:
        raise ConflitArchive("Cette année académique n'est pas archivée.")
    annee.archivee, annee.archivee_le, annee.archivee_par = False, None, None
    annee.save(update_fields=['archivee', 'archivee_le', 'archivee_par'])
    audit_log(request, 'desarchivage_annee', cible=annee, etablissement=annee.etablissement,
              details={'libelle': annee.libelle})
