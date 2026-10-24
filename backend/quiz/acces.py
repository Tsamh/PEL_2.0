"""Accès des étudiants aux quiz : affectation (classes, groupes, étudiants) et code d'accès."""
from django.db.models import Q

from .models import Quiz


def q_quiz_affecte(user):
    """Q vrai pour les quiz affectés à l'étudiant : par une de ses classes, un de ses groupes ou nominativement."""
    return (
        Q(pk__in=Quiz.objects.filter(classes__inscriptions__etudiant=user).values('pk'))
        | Q(pk__in=Quiz.objects.filter(groupes__membres=user).values('pk'))
        | Q(pk__in=Quiz.objects.filter(etudiants=user).values('pk'))
    )
