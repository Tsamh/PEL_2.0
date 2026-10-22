from rest_framework import viewsets

from accounts.permissions import RolePermission, CREATEURS, TOUS_LES_ROLES, ETUDIANT
from accounts.scoping import (
    EtablissementScopedMixin, filieres_etudiant, q_evaluation_etablissement,
    verifier_filiere_du_perimetre, verifier_references_evaluation,
)
from audit.services import log as audit_log
from .models import Quiz, Question, Choix
from .serializers import QuizSerializer, QuizEtudiantSerializer, QuestionReadSerializer, ChoixSerializer


def etablissement_evaluation(instance):
    if instance.filiere_id:
        return instance.filiere.etablissement
    return getattr(instance.cree_par, 'etablissement', None)


class QuizViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Quiz.objects.select_related('filiere', 'niveau', 'annee_academique', 'cree_par').all()
    serializer_class = QuizSerializer
    permission_classes = [RolePermission(read=TOUS_LES_ROLES, write=CREATEURS)]

    def get_serializer_class(self):
        if self.request.user.role == ETUDIANT:
            return QuizEtudiantSerializer
        return QuizSerializer

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id))

    def enseignant_scope(self, qs, user):
        return qs.filter(cree_par=user)

    def etudiant_scope(self, qs, user):
        return qs.filter(est_publie=True, filiere_id__in=filieres_etudiant(user))

    def perform_create(self, serializer, **kwargs):
        verifier_filiere_du_perimetre(self.request.user, serializer.validated_data.get('filiere'))
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        instance = super().perform_create(serializer, cree_par=self.request.user, **kwargs)
        if instance.est_publie:
            self._journaliser('publication_evaluation', instance)
        return instance

    def perform_update(self, serializer, **kwargs):
        if 'filiere' in serializer.validated_data:
            verifier_filiere_du_perimetre(self.request.user, serializer.validated_data['filiere'])
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        etait_publie = serializer.instance.est_publie
        instance = super().perform_update(serializer, **kwargs)
        if instance.est_publie and not etait_publie:
            self._journaliser('publication_evaluation', instance)
        return instance

    def perform_destroy(self, instance):
        self._journaliser('suppression_evaluation', instance)
        instance.delete()

    def _journaliser(self, action, instance):
        audit_log(self.request, action, cible=instance, etablissement=etablissement_evaluation(instance),
                  details={'type': 'quiz', 'titre': instance.titre})


class QuestionViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Question.objects.prefetch_related('choix').all()
    serializer_class = QuestionReadSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=CREATEURS)]

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id, prefix='quiz__'))

    def enseignant_scope(self, qs, user):
        return qs.filter(quiz__cree_par=user)


class ChoixViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Choix.objects.all()
    serializer_class = ChoixSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=CREATEURS)]

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id, prefix='question__quiz__'))

    def enseignant_scope(self, qs, user):
        return qs.filter(question__quiz__cree_par=user)
