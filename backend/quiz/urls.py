from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuizViewSet, QuestionViewSet, ChoixViewSet, TentativeViewSet, ReponseViewSet
from .views_banque import QuestionBanqueViewSet
from .views_sessions import SessionQuizViewSet
from .views_statistiques import ResultatsEtudiantView
from .views_suivi import SuiviAbsencesView, SuiviEvaluationsView, SuiviView

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet)
router.register(r'questions', QuestionViewSet)
router.register(r'choix', ChoixViewSet)
router.register(r'tentatives', TentativeViewSet, basename='tentative')
router.register(r'reponses', ReponseViewSet, basename='reponse')
router.register(r'banque', QuestionBanqueViewSet, basename='banque')
router.register(r'sessions-quiz', SessionQuizViewSet, basename='session-quiz')

urlpatterns = [
    path('etudiants/<int:pk>/resultats/', ResultatsEtudiantView.as_view(), name='resultats-etudiant'),
    path('suivi/', SuiviView.as_view(), name='suivi'),
    path('suivi/evaluations/', SuiviEvaluationsView.as_view(), name='suivi-evaluations'),
    path('suivi/absences/', SuiviAbsencesView.as_view(), name='suivi-absences'),
    path('', include(router.urls)),
]
