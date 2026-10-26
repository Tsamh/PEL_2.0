from django.utils import timezone
from rest_framework import viewsets

from accounts.permissions import CREATEURS, RolePermission
from accounts.scoping import EtablissementScopedMixin, en_entier, q_evaluation_etablissement
from audit.services import log as audit_log
from referentiel.archives import ArchiveMixin

from .banque import ENTIER_MAX
from .models import SessionQuiz
from .serializers_sessions import SessionQuizSerializer


def _identifiant(params, cle):
    valeur = en_entier(params.get(cle))
    return valeur if valeur is not None and 1 <= valeur <= ENTIER_MAX else None


class SessionQuizViewSet(ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
    annee_path = 'quiz__annee_academique'
    queryset = (
        SessionQuiz.objects.select_related('quiz', 'periode')
        .prefetch_related('classes', 'groupes__classe', 'etudiants').order_by('ouverture', 'id')
    )
    serializer_class = SessionQuizSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=CREATEURS)]

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id, prefix='quiz__'))

    def enseignant_scope(self, qs, user):
        return qs.filter(quiz__cree_par=user)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        quiz = _identifiant(params, 'quiz')
        periode = _identifiant(params, 'periode')
        if quiz:
            qs = qs.filter(quiz_id=quiz)
        if periode:
            qs = qs.filter(periode_id=periode)
        if params.get('a_venir') == '1':
            qs = qs.filter(fermeture__gte=timezone.now())
        return qs

    def _journaliser(self, action, session):
        audit_log(self.request, 'session_quiz', cible=session,
                  details={'action': action, 'quiz': session.quiz_id, 'type': session.type})

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
