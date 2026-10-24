from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuizViewSet, QuestionViewSet, ChoixViewSet, TentativeViewSet, ReponseViewSet
from .views_banque import QuestionBanqueViewSet
from .views_statistiques import ResultatsEtudiantView

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet)
router.register(r'questions', QuestionViewSet)
router.register(r'choix', ChoixViewSet)
router.register(r'tentatives', TentativeViewSet, basename='tentative')
router.register(r'reponses', ReponseViewSet, basename='reponse')
router.register(r'banque', QuestionBanqueViewSet, basename='banque')

urlpatterns = [
    path('etudiants/<int:pk>/resultats/', ResultatsEtudiantView.as_view(), name='resultats-etudiant'),
    path('', include(router.urls)),
]
