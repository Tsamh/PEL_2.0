from rest_framework import status
from rest_framework.exceptions import APIException

MESSAGE_VERROU = "Ce quiz a déjà des tentatives : ses questions et ses choix ne peuvent plus être modifiés."


class Conflit(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Action impossible dans l'état actuel."
    default_code = 'conflit'


def verifier_quiz_modifiable(quiz):
    if quiz.tentatives.exists():
        raise Conflit(MESSAGE_VERROU)
