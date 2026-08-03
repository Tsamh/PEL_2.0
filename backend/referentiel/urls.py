from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EtablissementViewSet, AnneeAcademiqueViewSet, FiliereViewSet, NiveauViewSet,
    UEViewSet, ECViewSet, CoursViewSet,
    ClasseViewSet, GroupeViewSet, InscriptionViewSet,
    EnseignantMatiereViewSet
)

router = DefaultRouter()
router.register(r'etablissements', EtablissementViewSet)
router.register(r'annees-academiques', AnneeAcademiqueViewSet)
router.register(r'filieres', FiliereViewSet)
router.register(r'niveaux', NiveauViewSet)
router.register(r'ues', UEViewSet)
router.register(r'ecs', ECViewSet)
router.register(r'cours', CoursViewSet)
router.register(r'classes', ClasseViewSet)
router.register(r'groupes', GroupeViewSet)
router.register(r'inscriptions', InscriptionViewSet)
router.register(r'enseignants-matieres', EnseignantMatiereViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
