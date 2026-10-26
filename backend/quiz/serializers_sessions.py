from django.utils import timezone
from rest_framework import serializers

from .models import SessionQuiz
from .statistiques import etudiants_affectes, quizzes_du_perimetre


def _nom(user):
    return user.get_full_name() or user.username


class SessionBaseSerializer(serializers.ModelSerializer):
    """Session ou rattrapage d'une évaluation (quiz ou devoir), commun aux deux.

    Une sous-classe donne `Meta.model` (modèle de session avec les constantes `NORMALE` et `RATTRAPAGE`),
    `champ_evaluation` (clé étrangère vers l'évaluation), `libelle_evaluation` (nom commun employé
    dans les messages, masculin) et définit `evaluations_du_perimetre(user)` et
    `concernes_rattrapage(evaluation)` (identifiants des étudiants qu'un rattrapage peut viser).
    """
    champ_evaluation = 'quiz'
    libelle_evaluation = 'quiz'

    periode_libelle = serializers.CharField(source='periode.libelle', read_only=True, default=None)
    classes_detail = serializers.SerializerMethodField()
    groupes_detail = serializers.SerializerMethodField()
    etudiants_detail = serializers.SerializerMethodField()
    nb_etudiants = serializers.SerializerMethodField()

    def evaluations_du_perimetre(self, user):
        raise NotImplementedError

    def concernes_rattrapage(self, evaluation):
        raise NotImplementedError

    def get_classes_detail(self, session):
        return [{'id': c.id, 'code': c.code, 'libelle': c.libelle} for c in session.classes.all()]

    def get_groupes_detail(self, session):
        return [{'id': g.id, 'code': g.code, 'libelle': g.libelle, 'classe_code': g.classe.code} for g in session.groupes.all()]

    def get_etudiants_detail(self, session):
        return [{'id': u.id, 'nom': _nom(u)} for u in session.etudiants.all()]

    def get_nb_etudiants(self, session):
        return len(session.etudiants.all())

    def _valeur(self, attrs, cle):
        if cle in attrs:
            return attrs[cle]
        if self.instance is None:
            return None
        valeur = getattr(self.instance, cle)
        return list(valeur.all()) if cle in ('classes', 'groupes', 'etudiants') else valeur

    def validate(self, attrs):
        champ, libelle = self.champ_evaluation, self.libelle_evaluation
        evaluation = self._valeur(attrs, champ)
        if self.instance is not None and champ in attrs and attrs[champ] != getattr(self.instance, champ):
            raise serializers.ValidationError({champ: [f"Le {libelle} d'une session ne peut pas être changé."]})
        request = self.context['request']
        if evaluation is None or not self.evaluations_du_perimetre(request.user).filter(pk=evaluation.pk).exists():
            raise serializers.ValidationError({champ: [f"Ce {libelle} ne fait pas partie de votre périmètre."]})
        ouverture, fermeture = self._valeur(attrs, 'ouverture'), self._valeur(attrs, 'fermeture')
        if ouverture and fermeture and fermeture <= ouverture:
            raise serializers.ValidationError({'fermeture': ["La fermeture doit suivre l'ouverture."]})
        periode = self._valeur(attrs, 'periode')
        if periode is not None:
            etablissement = evaluation.etablissement
            if etablissement is None or periode.semestre.annee_academique.etablissement_id != etablissement.pk:
                raise serializers.ValidationError({'periode': [f"Cette période ne fait pas partie de l'établissement du {libelle}."]})
            if ouverture and fermeture and (
                timezone.localtime(ouverture).date() < periode.date_debut
                or timezone.localtime(fermeture).date() > periode.date_fin
            ):
                raise serializers.ValidationError({'periode': ["La session doit tenir dans les dates de la période."]})
        classes = self._valeur(attrs, 'classes') or []
        groupes = self._valeur(attrs, 'groupes') or []
        etudiants = self._valeur(attrs, 'etudiants') or []
        if self._valeur(attrs, 'type') == self.Meta.model.RATTRAPAGE:
            self._verifier_rattrapage(evaluation, classes, groupes, etudiants)
        else:
            self._verifier_normale(evaluation, classes, groupes, etudiants)
        return attrs

    def _verifier_normale(self, evaluation, classes, groupes, etudiants):
        libelle = self.libelle_evaluation
        if etudiants:
            raise serializers.ValidationError({'etudiants': ["Une session vise des classes ou des groupes ; utilisez un rattrapage pour des étudiants."]})
        if not classes and not groupes:
            raise serializers.ValidationError({'classes': ["Choisissez au moins une classe ou un groupe."]})
        affectees = set(evaluation.classes.values_list('pk', flat=True))
        groupes_affectes = set(evaluation.groupes.values_list('pk', flat=True))
        erreurs = {}
        for classe in classes:
            if classe.pk not in affectees:
                erreurs.setdefault('classes', []).append(f"La classe {classe.pk} n'est pas affectée à ce {libelle}.")
        for groupe in groupes:
            if groupe.pk not in groupes_affectes and groupe.classe_id not in affectees:
                erreurs.setdefault('groupes', []).append(f"Le groupe {groupe.pk} n'est pas affecté à ce {libelle}.")
        if erreurs:
            raise serializers.ValidationError(erreurs)

    def _verifier_rattrapage(self, evaluation, classes, groupes, etudiants):
        if classes or groupes:
            raise serializers.ValidationError({'classes': ["Un rattrapage vise des étudiants, pas des classes ni des groupes."]})
        if not etudiants:
            raise serializers.ValidationError({'etudiants': ["Choisissez au moins un étudiant."]})
        concernes = set(self.concernes_rattrapage(evaluation))
        refuses = [f"Le compte {e.pk} n'est pas concerné par ce {self.libelle_evaluation}."
                   for e in etudiants if e.pk not in concernes]
        if refuses:
            raise serializers.ValidationError({'etudiants': refuses})


class SessionQuizSerializer(SessionBaseSerializer):
    champ_evaluation = 'quiz'
    libelle_evaluation = 'quiz'

    quiz_titre = serializers.CharField(source='quiz.titre', read_only=True)

    class Meta:
        model = SessionQuiz
        fields = '__all__'
        read_only_fields = ['cree_par', 'date_creation']

    def evaluations_du_perimetre(self, user):
        return quizzes_du_perimetre(user)

    def concernes_rattrapage(self, quiz):
        """Étudiants affectés au quiz ou ayant déjà une tentative."""
        concernes = set(etudiants_affectes(quiz).values_list('pk', flat=True))
        return concernes | set(quiz.tentatives.values_list('etudiant_id', flat=True))
