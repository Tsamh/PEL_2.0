from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DevoirViewSet, SoumissionDevoirViewSet, NoteMatiereViewSet
from .views_execution import ExecutionViewSet
from .views_sessions import SessionDevoirViewSet

router = DefaultRouter()
router.register(r'devoirs', DevoirViewSet)
router.register(r'soumissions', SoumissionDevoirViewSet)
router.register(r'sessions-devoir', SessionDevoirViewSet, basename='session-devoir')
router.register(r'notes', NoteMatiereViewSet)
router.register(r'executions', ExecutionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
