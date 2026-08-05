from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DevoirViewSet, SoumissionDevoirViewSet, NoteMatiereViewSet

router = DefaultRouter()
router.register(r'devoirs', DevoirViewSet)
router.register(r'soumissions', SoumissionDevoirViewSet)
router.register(r'notes', NoteMatiereViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
