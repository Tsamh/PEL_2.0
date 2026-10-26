from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CREATEURS, RolePermission
from accounts.scoping import en_entier

from . import suivi


def _regroupement(request):
    regroupement = request.query_params.get('regroupement', 'classe')
    if regroupement not in suivi.REGROUPEMENTS:
        raise ValidationError({'regroupement': ["Regroupement inconnu."]})
    return regroupement


def _contexte(request, quizzes=None):
    params = request.query_params
    if quizzes is None:
        quizzes = suivi.quizzes_suivis(request.user, params)
    return suivi.charger(quizzes, classe=en_entier(params.get('classe')))


class SuiviView(APIView):
    """Synthèse de participation, absences et retards par regroupement."""
    permission_classes = [RolePermission(read=CREATEURS)]

    def get(self, request):
        regroupement = _regroupement(request)
        return Response(suivi.synthese(_contexte(request), regroupement))


class SuiviEvaluationsView(APIView):
    """Indicateurs par quiz, éventuellement limités à un groupe."""
    permission_classes = [RolePermission(read=CREATEURS)]

    def get(self, request):
        regroupement = _regroupement(request)
        return Response(suivi.evaluations(_contexte(request), regroupement, request.query_params.get('groupe')))


class SuiviAbsencesView(APIView):
    """Absents et retardataires d'un quiz du périmètre ; `classe`, `regroupement` et `groupe` limitent les lignes."""
    permission_classes = [RolePermission(read=CREATEURS)]

    def get(self, request):
        pk = en_entier(request.query_params.get('quiz'))
        if pk is None:
            raise ValidationError({'quiz': ["Indiquez le quiz."]})
        groupe = request.query_params.get('groupe')
        regroupement = _regroupement(request) if groupe else None
        qs = suivi.quizzes_suivis(request.user, {}, masquer=False)
        quiz = get_object_or_404(qs, pk=pk)
        return Response(suivi.absences(_contexte(request, qs.filter(pk=pk)), quiz, regroupement, groupe))
