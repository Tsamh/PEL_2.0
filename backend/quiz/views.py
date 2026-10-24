from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import RolePermission, CREATEURS, TOUS_LES_ROLES, ETUDIANT, IsEtudiant
from accounts.scoping import (
    EtablissementScopedMixin, en_entier, q_evaluation_etablissement,
    verifier_filiere_du_perimetre, verifier_references_evaluation,
)
from audit.services import log as audit_log
from . import acces, passage
from .correction import arrondir, en_decimal, recalculer_score
from .exceptions import Conflit, verifier_quiz_modifiable
from .models import Quiz, Question, Choix, TentativeQuiz, ReponseQuiz
from .serializers import (
    QuizSerializer, QuizEtudiantSerializer, QuestionReadSerializer, ChoixSerializer, TentativeEtudiantSerializer,
    TentativeEnseignantSerializer, ReponseCorrectionSerializer,
)


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
        return qs.filter(est_publie=True).filter(acces.q_quiz_affecte(user))

    def _cloturer_expirees_etudiant(self, request):
        # L'état (tentative en cours, dernière tentative) doit refléter les tentatives expirées.
        if request.user.role == ETUDIANT:
            passage.cloturer_expirees(TentativeQuiz.objects.filter(etudiant=request.user))

    def list(self, request, *args, **kwargs):
        self._cloturer_expirees_etudiant(request)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        self._cloturer_expirees_etudiant(request)
        return super().retrieve(request, *args, **kwargs)

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

    @action(detail=True, methods=['post'], permission_classes=[IsEtudiant])
    def demarrer(self, request, pk=None):
        quiz = self.get_object()
        tentative, creee = passage.demarrer(quiz, request.user)
        if creee:
            audit_log(request, 'demarrage_quiz', cible=tentative, details={'quiz': quiz.titre, 'numero': tentative.numero})
        data = TentativeEtudiantSerializer(tentative, context={'request': request}).data
        return Response(data, status=status.HTTP_201_CREATED if creee else status.HTTP_200_OK)

    @action(detail=True, methods=['get'], permission_classes=[RolePermission(read=CREATEURS)])
    def tentatives(self, request, pk=None):
        quiz = self.get_object()
        passage.cloturer_expirees(quiz.tentatives.all())
        tentatives = list(
            quiz.tentatives.select_related('etudiant').prefetch_related('reponses')
            .order_by('etudiant__last_name', 'etudiant__first_name', 'etudiant__username', 'numero')
        )
        par_etudiant = {}
        for t in tentatives:
            par_etudiant.setdefault(t.etudiant_id, []).append(t)
        meilleures = {m.id for m in (passage.meilleure_tentative(ts) for ts in par_etudiant.values()) if m}
        return Response(TentativeEnseignantSerializer(tentatives, many=True, context={'meilleures': meilleures}).data)

    @action(detail=True, methods=['post'], permission_classes=[RolePermission(write=CREATEURS)])
    def publier_resultats(self, request, pk=None):
        quiz = self.get_object()
        if quiz.publication_resultats != Quiz.PUBLICATION_DIFFEREE:
            raise Conflit("Les résultats de ce quiz sont publiés automatiquement après chaque soumission.")
        if quiz.resultats_publies:
            raise Conflit("Les résultats de ce quiz sont déjà publiés.")
        quiz.resultats_publies = True
        quiz.save(update_fields=['resultats_publies'])
        audit_log(request, 'publication_resultats', cible=quiz, details={'titre': quiz.titre})
        return Response({'resultats_publies': True})

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

    def perform_create(self, serializer, **kwargs):
        with transaction.atomic():
            instance = super().perform_create(serializer, **kwargs)
            verifier_quiz_modifiable(instance.quiz)
        return instance

    def perform_update(self, serializer, **kwargs):
        verifier_quiz_modifiable(serializer.instance.quiz)
        with transaction.atomic():
            instance = super().perform_update(serializer, **kwargs)
            verifier_quiz_modifiable(instance.quiz)
        return instance

    def perform_destroy(self, instance):
        verifier_quiz_modifiable(instance.quiz)
        instance.delete()


class ChoixViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Choix.objects.all()
    serializer_class = ChoixSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=CREATEURS)]

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id, prefix='question__quiz__'))

    def enseignant_scope(self, qs, user):
        return qs.filter(question__quiz__cree_par=user)

    def perform_create(self, serializer, **kwargs):
        with transaction.atomic():
            instance = super().perform_create(serializer, **kwargs)
            verifier_quiz_modifiable(instance.question.quiz)
        return instance

    def perform_update(self, serializer, **kwargs):
        verifier_quiz_modifiable(serializer.instance.question.quiz)
        with transaction.atomic():
            instance = super().perform_update(serializer, **kwargs)
            verifier_quiz_modifiable(instance.question.quiz)
        return instance

    def perform_destroy(self, instance):
        verifier_quiz_modifiable(instance.question.quiz)
        instance.delete()


class TentativeViewSet(viewsets.ReadOnlyModelViewSet):
    """Tentatives de l'étudiant connecté. La tentative d'un autre étudiant renvoie 404."""
    serializer_class = TentativeEtudiantSerializer
    permission_classes = [IsEtudiant]

    def get_queryset(self):
        return TentativeQuiz.objects.filter(etudiant=self.request.user).select_related('quiz')

    def get_object(self):
        tentative = super().get_object()
        passage.cloturer_si_expiree(tentative)
        return tentative

    def list(self, request, *args, **kwargs):
        passage.cloturer_expirees(self.get_queryset())
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['put'])
    def repondre(self, request, pk=None):
        tentative = super().get_object()
        passage.enregistrer_reponse(tentative, request.data)
        return Response({'enregistre': True})

    @action(detail=True, methods=['post'])
    def soumettre(self, request, pk=None):
        tentative = super().get_object()
        if tentative.statut == TentativeQuiz.SOUMISE:
            raise Conflit("Cette tentative est déjà soumise.")
        passage.soumettre(tentative, auto=passage.est_expiree(tentative), request=request)
        return Response(self.get_serializer(tentative).data)


class ReponseViewSet(EtablissementScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Réponses courtes des tentatives soumises, pour la validation par l'enseignant."""
    queryset = (
        ReponseQuiz.objects
        .filter(question__type_question='courte', tentative__statut=TentativeQuiz.SOUMISE)
        .select_related('question', 'tentative__etudiant', 'tentative__quiz')
        .prefetch_related('question__choix')
        .order_by('tentative__quiz_id', 'question__ordre', 'id')
    )
    serializer_class = ReponseCorrectionSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=CREATEURS)]

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id, prefix='tentative__quiz__'))

    def enseignant_scope(self, qs, user):
        return qs.filter(tentative__quiz__cree_par=user)

    def filter_queryset(self, qs):
        params = self.request.query_params
        if 'quiz' in params:
            quiz_id = en_entier(params['quiz'])
            qs = qs.filter(tentative__quiz_id=quiz_id) if quiz_id is not None else qs.none()
        statut = params.get('statut')
        if statut in (ReponseQuiz.AUTO, ReponseQuiz.A_VALIDER, ReponseQuiz.VALIDEE):
            qs = qs.filter(statut_correction=statut)
        return qs

    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        reponse = self.get_object()
        maximum = reponse.question.points
        brut = request.data.get('score') if isinstance(request.data, dict) else None
        score = en_decimal(brut)
        if score is None or score < 0 or score > maximum:
            raise ValidationError({'detail': f"La note doit être un nombre compris entre 0 et {maximum}."})
        avant = reponse.score_obtenu
        with transaction.atomic():
            tentative = TentativeQuiz.objects.select_for_update().get(pk=reponse.tentative_id)
            reponse.score_obtenu = arrondir(score)
            reponse.statut_correction = ReponseQuiz.VALIDEE
            reponse.corrige_par = request.user
            reponse.corrige_le = timezone.now()
            reponse.save(update_fields=['score_obtenu', 'statut_correction', 'corrige_par', 'corrige_le'])
            recalculer_score(tentative)
        audit_log(request, 'validation_reponse', cible=tentative,
                  details={'question': reponse.question_id, 'avant': str(avant), 'apres': str(reponse.score_obtenu)})
        return Response(self.get_serializer(reponse).data)
