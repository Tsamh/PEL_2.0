from rest_framework import viewsets, permissions
from .models import Quiz, Question, Choix
from .serializers import QuizSerializer, QuestionReadSerializer, ChoixSerializer


class QuizViewSet(viewsets.ModelViewSet):
    queryset = Quiz.objects.select_related('filiere', 'niveau', 'annee_academique', 'cree_par').all()
    serializer_class = QuizSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role in ('admin', 'responsable_formation') and user.etablissement:
            qs = qs.filter(filiere__etablissement=user.etablissement)
        elif user.role == 'enseignant':
            qs = qs.filter(cree_par=user)
        elif user.role == 'etudiant':
            qs = qs.filter(est_publie=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.prefetch_related('choix').all()
    serializer_class = QuestionReadSerializer


class ChoixViewSet(viewsets.ModelViewSet):
    queryset = Choix.objects.all()
    serializer_class = ChoixSerializer
