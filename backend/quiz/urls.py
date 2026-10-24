from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuizViewSet, QuestionViewSet, ChoixViewSet, TentativeViewSet, ReponseViewSet

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet)
router.register(r'questions', QuestionViewSet)
router.register(r'choix', ChoixViewSet)
router.register(r'tentatives', TentativeViewSet, basename='tentative')
router.register(r'reponses', ReponseViewSet, basename='reponse')

urlpatterns = [
    path('', include(router.urls)),
]
