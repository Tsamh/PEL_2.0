from django.utils import timezone
from rest_framework import viewsets

from accounts.permissions import CREATEURS, RolePermission
from accounts.scoping import EtablissementScopedMixin, en_entier, q_evaluation_etablissement
from audit.services import log as audit_log
from quiz.banque import ENTIER_MAX
from referentiel.archives import ArchiveMixin

from .models import SessionDevoir
from .serializers_sessions import SessionDevoirSerializer


def _identifiant(params, cle):
    valeur = en_entier(params.get(cle))
    return valeur if valeur is not None and 1 <= valeur <= ENTIER_MAX else None


class SessionDevoirViewSet(ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
    annee_path = 'devoir__annee_academique'
    parent_params = ('devoir',)
    queryset = (
        SessionDevoir.objects.select_related('devoir', 'periode')
        .prefetch_related('classes', 'groupes__classe', 'etudiants').order_by('ouverture', 'id')
    )
    serializer_class = SessionDevoirSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=CREATEURS)]

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id, prefix='devoir__'))

    def enseignant_scope(self, qs, user):
        return qs.filter(devoir__cree_par=user)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        devoir = _identifiant(params, 'devoir')
        periode = _identifiant(params, 'periode')
        if devoir:
            qs = qs.filter(devoir_id=devoir)
        if periode:
            qs = qs.filter(periode_id=periode)
        if params.get('a_venir') == '1':
            qs = qs.filter(fermeture__gte=timezone.now())
        return qs

    def _journaliser(self, action, session):
        audit_log(self.request, 'session_quiz', cible=session,
                  details={'action': action, 'devoir': session.devoir_id, 'type': 'devoir', 'type_session': session.type})

    def perform_create(self, serializer, **kwargs):
        session = super().perform_create(serializer, cree_par=self.request.user, **kwargs)
        self._journaliser('creation', session)
        return session

    def perform_update(self, serializer, **kwargs):
        session = super().perform_update(serializer, **kwargs)
        self._journaliser('modification', session)
        return session

    def perform_destroy(self, session):
        self._journaliser('suppression', session)
        session.delete()
