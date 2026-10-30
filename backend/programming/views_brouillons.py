"""Brouillons d'exercices : lecture et auto-sauvegarde par l'étudiant (action `brouillons` du devoir)."""
from django.db import IntegrityError, transaction
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.permissions import IsEtudiant
from accounts.scoping import en_entier
from quiz.exceptions import Conflit
from .execution.langages import message_principal
from .models import BrouillonExercice, SoumissionDevoir
from .serializers import valider_fichiers
from .views_execution import MESSAGE_EXERCICE, verifier_limite

LIMITE_BROUILLONS_PAR_MINUTE = 60
MESSAGE_TROP_ENREGISTREMENTS = "Trop d'enregistrements : patientez une minute."


def enregistrer(etudiant, exercice, fichiers):
    """Écrit le brouillon (dernier enregistrement gagnant) ; deux premières écritures simultanées ne font pas d'erreur."""
    for tentative in range(2):
        try:
            with transaction.atomic():
                brouillon, _ = BrouillonExercice.objects.update_or_create(
                    etudiant=etudiant, exercice=exercice, defaults={'fichiers': fichiers})
            return brouillon
        except IntegrityError:
            # La contrainte d'unicité a tranché : la ligne existe maintenant, la seconde tentative la met à jour.
            if tentative:
                raise


class BrouillonsMixin:
    @action(detail=True, methods=['get', 'put'], permission_classes=[IsEtudiant])
    def brouillons(self, request, pk=None):
        """GET : `[{exercice, fichiers, modifie_le}]`. PUT `{exercice, fichiers}` -> 200 `{exercice, modifie_le}`.

        Ordre des refus du PUT : devoir visible (404), rôle (403), année archivée (409), fenêtre (409), 60 par minute
        (429), corps, exercice et fichiers (400), soumission existante (409).
        """
        devoir = self.get_object()
        if request.method == 'GET':
            lignes = BrouillonExercice.objects.filter(etudiant=request.user, exercice__devoir=devoir).order_by(
                'exercice__ordre', 'exercice_id')
            return Response([{'exercice': b.exercice_id, 'fichiers': b.fichiers, 'modifie_le': b.modifie_le}
                             for b in lignes])
        from .views import MESSAGE_DEJA_SOUMIS, MESSAGE_NOTE_VALIDEE, verifier_fenetre_ouverte
        self.verifier_ecriture(devoir)
        verifier_fenetre_ouverte(devoir, request.user)
        verifier_limite(request.user, 'brouillons', LIMITE_BROUILLONS_PAR_MINUTE, MESSAGE_TROP_ENREGISTREMENTS)
        donnees = request.data
        if not isinstance(donnees, dict):
            raise ValidationError("Le corps de la requête doit être un objet JSON.")
        exercice_id = en_entier(donnees.get('exercice'))
        exercice = devoir.exercices.filter(pk=exercice_id).first() if exercice_id is not None else None
        if exercice is None:
            raise ValidationError({'exercice': [MESSAGE_EXERCICE]})
        try:
            fichiers = valider_fichiers(donnees.get('fichiers'))
        except ValidationError as erreur:
            raise ValidationError({'fichiers': erreur.detail})
        manque = message_principal(devoir.langage, fichiers)
        if manque:
            raise ValidationError({'fichiers': [manque]})
        soumission = devoir.soumissions.filter(etudiant=request.user).first()
        if soumission is not None:
            if not devoir.resoumission_autorisee:
                raise Conflit(MESSAGE_DEJA_SOUMIS)
            if soumission.statut == SoumissionDevoir.CORRIGE:
                raise Conflit(MESSAGE_NOTE_VALIDEE)
        brouillon = enregistrer(request.user, exercice, fichiers)
        return Response({'exercice': exercice.pk, 'modifie_le': brouillon.modifie_le})
