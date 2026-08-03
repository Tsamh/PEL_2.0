from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DevoirViewSet, SoumissionDevoirViewSet

router = DefaultRouter()
router.register(r'devoirs', DevoirViewSet)
router.register(r'soumissions', SoumissionDevoirViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
