from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CREATEURS, RolePermission

from . import passage, statistiques
from .models import TentativeQuiz


class ResultatsEtudiantView(APIView):
    """Résultats d'un étudiant du périmètre sur les quiz du périmètre de l'acteur."""
    permission_classes = [RolePermission(read=CREATEURS)]

    def get(self, request, pk):
        etudiant = get_object_or_404(statistiques.etudiants_du_perimetre(request.user), pk=pk)
        quizzes = statistiques.quizzes_du_perimetre(request.user)
        passage.cloturer_expirees(TentativeQuiz.objects.filter(etudiant=etudiant, quiz__in=quizzes))
        return Response(statistiques.resultats_etudiant(etudiant, quizzes))
