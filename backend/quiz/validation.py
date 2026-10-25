"""Validation des quiz avant publication : règles de publication et décisions du responsable de formation."""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.permissions import ADMIN, RESPONSABLE, SUPERADMIN
from audit.services import log as audit_log

from .banque import contenu_normalise, contenu_question
from .exceptions import Conflit
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


MOTIF_MAX = 2000


def _nom(user):
    return user.get_full_name() or user.username


def _envoyer(sujet, lignes, destinataires):
    adresses = [u.email for u in destinataires if u is not None and u.email]
    if adresses:
        send_mail(sujet, "\n".join(lignes), settings.DEFAULT_FROM_EMAIL, adresses, fail_silently=True)


def soumettre(quiz, request):
    if not validation_requise(quiz.etablissement):
        raise Conflit("La validation n'est pas requise pour ce quiz : publiez-le directement.")
    if quiz.statut_validation == Quiz.EN_ATTENTE:
        raise Conflit("Ce quiz est déjà en attente de validation.")
    if quiz.statut_validation == Quiz.VALIDEE:
        raise Conflit("Ce quiz est déjà validé.")
    if not quiz.questions.exists():
        raise ValidationError({'detail': "Ajoutez au moins une question avant de soumettre le quiz."})
    quiz.statut_validation = Quiz.EN_ATTENTE
    quiz.soumis_le = timezone.now()
    quiz.motif_refus = ''
    quiz.save(update_fields=['statut_validation', 'soumis_le', 'motif_refus'])
    audit_log(request, 'soumission_validation', cible=quiz, details={'titre': quiz.titre})
    responsables = get_user_model().objects.filter(role=RESPONSABLE, etablissement=quiz.etablissement, is_active=True)
    _envoyer(f"Quiz à valider : {quiz.titre}", [
        "Bonjour,", "",
        f"{_nom(request.user)} a soumis le quiz « {quiz.titre} » pour validation avant publication.",
        f"Pour le consulter : {settings.FRONTEND_URL}/validation-quiz",
        "", "L'équipe PEL",
    ], responsables)


def valider(quiz, request):
    if quiz.statut_validation != Quiz.EN_ATTENTE:
        raise Conflit("Ce quiz n'est pas en attente de validation.")
    quiz.statut_validation = Quiz.VALIDEE
    quiz.est_publie = True
    quiz.valide_par = request.user
    quiz.valide_le = timezone.now()
    quiz.motif_refus = ''
    quiz.save(update_fields=['statut_validation', 'est_publie', 'valide_par', 'valide_le', 'motif_refus'])
    audit_log(request, 'validation_quiz', cible=quiz, details={'titre': quiz.titre})
    _envoyer(f"Quiz validé : {quiz.titre}", [
        "Bonjour,", "",
        f"Votre quiz « {quiz.titre} » a été validé par {_nom(request.user)} et il est maintenant publié.",
        "", "L'équipe PEL",
    ], [quiz.cree_par])


def refuser(quiz, request, motif):
    motif = motif.strip() if isinstance(motif, str) else ''
    if not motif:
        raise ValidationError({'motif': ["Indiquez le motif du refus."]})
    if len(motif) > MOTIF_MAX:
        raise ValidationError({'motif': [f"Le motif ne doit pas dépasser {MOTIF_MAX} caractères."]})
    if quiz.statut_validation != Quiz.EN_ATTENTE:
        raise Conflit("Ce quiz n'est pas en attente de validation.")
    quiz.statut_validation = Quiz.REFUSEE
    quiz.est_publie = False
    quiz.motif_refus = motif
    quiz.valide_par = request.user
    quiz.valide_le = timezone.now()
    quiz.save(update_fields=['statut_validation', 'est_publie', 'motif_refus', 'valide_par', 'valide_le'])
    audit_log(request, 'refus_quiz', cible=quiz, details={'titre': quiz.titre, 'motif': motif})
    _envoyer(f"Quiz à revoir : {quiz.titre}", [
        "Bonjour,", "",
        f"Votre quiz « {quiz.titre} » n'a pas été validé par {_nom(request.user)}.",
        f"Motif : {motif}",
        "Vous pouvez le corriger puis le soumettre de nouveau.",
        "", "L'équipe PEL",
    ], [quiz.cree_par])
