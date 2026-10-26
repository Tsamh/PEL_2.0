from rest_framework import serializers

from accounts.permissions import ADMIN, ENSEIGNANT, RESPONSABLE, SUPERADMIN
from accounts.scoping import q_evaluation_etablissement
from quiz.serializers_sessions import SessionBaseSerializer
from quiz.statistiques import etudiants_affectes

from .models import Devoir, SessionDevoir


def devoirs_du_perimetre(user):
    """Devoirs qu'un compte peut organiser : l'établissement pour la gestion, ses propres devoirs pour un enseignant."""
    qs = Devoir.objects.all()
    if user.role == SUPERADMIN:
        return qs
    if user.role in (ADMIN, RESPONSABLE):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id)) if user.etablissement_id else qs.none()
    if user.role == ENSEIGNANT:
        return qs.filter(cree_par=user)
    return qs.none()


class SessionDevoirSerializer(SessionBaseSerializer):
    champ_evaluation = 'devoir'
    libelle_evaluation = 'devoir'

    devoir_titre = serializers.CharField(source='devoir.titre', read_only=True)

    class Meta:
        model = SessionDevoir
        fields = '__all__'
        read_only_fields = ['cree_par', 'date_creation']

    def evaluations_du_perimetre(self, user):
        return devoirs_du_perimetre(user)

    def concernes_rattrapage(self, devoir):
        """Étudiants affectés au devoir qui ne l'ont pas soumis (une seule soumission par devoir).

        Les étudiants déjà visés par le rattrapage modifié restent acceptés, même s'ils ont soumis depuis.
        """
        concernes = set(etudiants_affectes(devoir).values_list('pk', flat=True))
        concernes -= set(devoir.soumissions.values_list('etudiant_id', flat=True))
        if self.instance is not None:
            concernes |= set(self.instance.etudiants.values_list('pk', flat=True))
        return concernes
