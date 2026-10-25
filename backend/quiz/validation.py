"""Validation des quiz avant publication : règles de publication et décisions du responsable de formation."""
from decimal import Decimal

from rest_framework.exceptions import ValidationError

from accounts.permissions import ADMIN, RESPONSABLE, SUPERADMIN

from .banque import contenu_normalise, contenu_question
from .models import Question, Quiz

MESSAGE_PUBLICATION = "La publication de ce quiz demande la validation du responsable de formation."
CHAMPS_CONTENU = ('titre', 'description', 'duree_minutes', 'tentatives_autorisees', 'reprise_autorisee',
                  'publication_resultats', 'afficher_corrige')
ROLES_GESTION = (SUPERADMIN, ADMIN, RESPONSABLE)


def validation_requise(etablissement):
    return bool(etablissement is not None and etablissement.validation_quiz_requise)


def etablissement_du_quiz(acteur, instance, attrs):
    """Établissement de la filière (nouvelle ou actuelle), sinon celui du créateur, sinon celui de l'acteur."""
    filiere = attrs['filiere'] if 'filiere' in attrs else (instance.filiere if instance is not None else None)
    if filiere is not None:
        return filiere.etablissement
    if instance is not None and instance.cree_par_id:
        return instance.cree_par.etablissement
    return acteur.etablissement


def _contenu_soumis(question):
    return contenu_normalise({
        'texte': question.get('texte', ''),
        'type_question': question.get('type_question', 'qcm'),
        'points': question.get('points', Decimal('1')),
        'mode_notation': question.get('mode_notation', Question.TOUT_OU_RIEN),
        'penalite': question.get('penalite', Decimal('0')),
        'explication': question.get('explication', ''),
        'choix': [
            {'texte': c.get('texte', ''), 'est_correct': c.get('est_correct', False), 'points': c.get('points', Decimal('0'))}
            for c in question.get('choix', [])
        ],
    })


def contenu_modifie(instance, attrs):
    """Vrai si la requête change le contenu du quiz (réglages de passage ou questions, comparées par contenu)."""
    if instance is None:
        return False
    if any(cle in attrs and attrs[cle] != getattr(instance, cle) for cle in CHAMPS_CONTENU):
        return True
    if 'questions' in attrs:
        actuelles = [contenu_question(q) for q in instance.questions.prefetch_related('choix').order_by('ordre', 'id')]
        return actuelles != [_contenu_soumis(q) for q in attrs['questions']]
    return False


def appliquer_regles(acteur, instance, attrs):
    """Règles de publication appliquées à `attrs` avant l'enregistrement d'un quiz (création ou modification)."""
    if acteur.role in ROLES_GESTION:
        if attrs.get('est_publie') is True:
            attrs['statut_validation'] = Quiz.VALIDEE
        return
    if not validation_requise(etablissement_du_quiz(acteur, instance, attrs)):
        return
    statut = instance.statut_validation if instance is not None else Quiz.BROUILLON
    if statut in (Quiz.VALIDEE, Quiz.EN_ATTENTE) and contenu_modifie(instance, attrs):
        # Un quiz validé ou en attente dont le contenu change repart en brouillon, dépublié.
        attrs['statut_validation'] = Quiz.BROUILLON
        attrs['est_publie'] = False
        return
    if attrs.get('est_publie') is True and statut != Quiz.VALIDEE:
        raise ValidationError({'est_publie': [MESSAGE_PUBLICATION]})
