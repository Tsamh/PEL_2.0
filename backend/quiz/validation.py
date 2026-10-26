"""Validation avant publication, commune aux quiz et aux devoirs : règles de publication et décisions
du responsable de formation.

Ce qui distingue un quiz d'un devoir (textes, contenu) est porté par un `Profil` ; les constantes de
statut (`BROUILLON`, `EN_ATTENTE`, `VALIDEE`, `REFUSEE`) sont lues sur la classe de l'objet.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

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


def etablissement_de(acteur, instance, attrs):
    """Établissement de la filière (nouvelle ou actuelle), sinon celui du créateur, sinon celui de l'acteur."""
    filiere = attrs['filiere'] if 'filiere' in attrs else (instance.filiere if instance is not None else None)
    if filiere is not None:
        return filiere.etablissement
    if instance is not None and instance.cree_par_id:
        return instance.cree_par.etablissement
    return acteur.etablissement


etablissement_du_quiz = etablissement_de


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


def _quiz_a_du_contenu(quiz):
    return quiz.questions.exists()


@dataclass(frozen=True)
class Profil:
    """Ce qui distingue une évaluation soumise à validation : textes et règles de contenu.

    `nom` est le nom commun (« quiz », « devoir ») et `article` sa forme démonstrative (« ce quiz »).
    `contenu_modifie(instance, attrs)` dit si une requête change le contenu ; `a_du_contenu(objet)` si
    l'évaluation peut être soumise. `modele` ne sert qu'à lire les constantes de statut à la création
    (aucun objet encore) ; à défaut, celles du quiz, identiques, s'appliquent.
    """
    nom: str
    article: str
    message_publication: str
    contenu_modifie: Callable
    a_du_contenu: Callable
    message_sans_contenu: str
    url_validation: str = '/validation-quiz'
    modele: Optional[type] = None

    @property
    def article_majuscule(self):
        return self.article[:1].upper() + self.article[1:]

    @property
    def nom_majuscule(self):
        return self.nom[:1].upper() + self.nom[1:]

    def details(self, objet, **extra):
        """Détails d'audit : le titre, puis `type` pour toute évaluation autre qu'un quiz."""
        details = {'titre': objet.titre, **extra}
        if self.nom != 'quiz':
            details['type'] = self.nom
        return details


PROFIL_QUIZ = Profil(
    nom='quiz',
    article='ce quiz',
    message_publication=MESSAGE_PUBLICATION,
    contenu_modifie=contenu_modifie,
    a_du_contenu=_quiz_a_du_contenu,
    message_sans_contenu="Ajoutez au moins une question avant de soumettre le quiz.",
    url_validation='/validation-quiz',
    modele=Quiz,
)


def _statuts(objet, profil):
    """Classe portant les constantes de statut : celle de l'objet, sinon celle du profil."""
    if objet is not None:
        return type(objet)
    return profil.modele or Quiz


def appliquer_regles(acteur, instance, attrs, profil=PROFIL_QUIZ):
    """Règles de publication appliquées à `attrs` avant l'enregistrement d'une évaluation (création ou modification)."""
    M = _statuts(instance, profil)
    if acteur.role in ROLES_GESTION:
        if attrs.get('est_publie') is True:
            if instance is None or instance.statut_validation != M.VALIDEE:
                attrs['valide_par'] = acteur
                attrs['valide_le'] = timezone.now()
                attrs['motif_refus'] = ''
            attrs['statut_validation'] = M.VALIDEE
        return
    requise = validation_requise(etablissement_de(acteur, instance, attrs))
    statut = instance.statut_validation if instance is not None else M.BROUILLON
    if profil.contenu_modifie(instance, attrs):
        # Un contenu modifié fait perdre la validation, avec ou sans réglage ; l'évaluation n'est dépubliée
        # que si l'établissement demande la validation.
        if requise and (instance.est_publie or statut in (M.VALIDEE, M.EN_ATTENTE)):
            attrs['statut_validation'] = M.BROUILLON
            attrs['est_publie'] = False
            return
        if statut in (M.VALIDEE, M.EN_ATTENTE):
            attrs['statut_validation'] = statut = M.BROUILLON
    if not requise:
        return
    deja_publie = instance is not None and instance.est_publie
    if attrs.get('est_publie') is True and not deja_publie and statut != M.VALIDEE:
        raise ValidationError({'est_publie': [profil.message_publication]})


def contenu_change_hors_formulaire(objet, acteur):
    """Contenu modifié par les routes dédiées (questions, choix, exercices) : mêmes conséquences qu'un
    contenu modifié dans le formulaire."""
    if acteur.role in ROLES_GESTION:
        return
    M = type(objet)
    champs = []
    if objet.statut_validation in (M.VALIDEE, M.EN_ATTENTE):
        objet.statut_validation = M.BROUILLON
        champs.append('statut_validation')
    if objet.est_publie and validation_requise(objet.etablissement):
        objet.est_publie = False
        champs.append('est_publie')
    if champs:
        objet.save(update_fields=champs)


MOTIF_MAX = 2000


def _nom(user):
    return user.get_full_name() or user.username


def _envoyer(sujet, lignes, destinataires):
    adresses = [u.email for u in destinataires if u is not None and u.email]
    if adresses:
        send_mail(sujet, "\n".join(lignes), settings.DEFAULT_FROM_EMAIL, adresses, fail_silently=True)


def soumettre(objet, request, profil=PROFIL_QUIZ):
    M = type(objet)
    if request.user.role in ROLES_GESTION:
        raise Conflit(f"Vous pouvez publier {profil.article} directement.")
    if not validation_requise(objet.etablissement):
        raise Conflit(f"La validation n'est pas requise pour {profil.article} : publiez-le directement.")
    if objet.statut_validation == M.EN_ATTENTE:
        raise Conflit(f"{profil.article_majuscule} est déjà en attente de validation.")
    if objet.statut_validation == M.VALIDEE:
        raise Conflit(f"{profil.article_majuscule} est déjà validé.")
    if not profil.a_du_contenu(objet):
        raise ValidationError({'detail': profil.message_sans_contenu})
    objet.statut_validation = M.EN_ATTENTE
    objet.soumis_le = timezone.now()
    objet.motif_refus = ''
    objet.save(update_fields=['statut_validation', 'soumis_le', 'motif_refus'])
    audit_log(request, 'soumission_validation', cible=objet, details=profil.details(objet))
    actifs = get_user_model().objects.filter(etablissement=objet.etablissement, is_active=True)
    responsables = actifs.filter(role=RESPONSABLE)
    if not any(u.email for u in responsables):
        responsables = actifs.filter(role=ADMIN)
    _envoyer(f"{profil.nom_majuscule} à valider : {objet.titre}", [
        "Bonjour,", "",
        f"{_nom(request.user)} a soumis le {profil.nom} « {objet.titre} » pour validation avant publication.",
        f"Pour le consulter : {settings.FRONTEND_URL}{profil.url_validation}",
        "", "L'équipe PEL",
    ], responsables)


def valider(objet, request, profil=PROFIL_QUIZ):
    M = type(objet)
    if objet.statut_validation != M.EN_ATTENTE:
        raise Conflit(f"{profil.article_majuscule} n'est pas en attente de validation.")
    objet.statut_validation = M.VALIDEE
    objet.est_publie = True
    objet.valide_par = request.user
    objet.valide_le = timezone.now()
    objet.motif_refus = ''
    objet.save(update_fields=['statut_validation', 'est_publie', 'valide_par', 'valide_le', 'motif_refus'])
    audit_log(request, 'validation_quiz', cible=objet, details=profil.details(objet))
    _envoyer(f"{profil.nom_majuscule} validé : {objet.titre}", [
        "Bonjour,", "",
        f"Votre {profil.nom} « {objet.titre} » a été validé par {_nom(request.user)} et il est maintenant publié.",
        "", "L'équipe PEL",
    ], [objet.cree_par])


def refuser(objet, request, motif, profil=PROFIL_QUIZ):
    motif = motif.strip() if isinstance(motif, str) else ''
    if not motif:
        raise ValidationError({'motif': ["Indiquez le motif du refus."]})
    if len(motif) > MOTIF_MAX:
        raise ValidationError({'motif': [f"Le motif ne doit pas dépasser {MOTIF_MAX} caractères."]})
    M = type(objet)
    if objet.statut_validation != M.EN_ATTENTE:
        raise Conflit(f"{profil.article_majuscule} n'est pas en attente de validation.")
    objet.statut_validation = M.REFUSEE
    objet.est_publie = False
    objet.motif_refus = motif
    objet.valide_par = request.user
    objet.valide_le = timezone.now()
    objet.save(update_fields=['statut_validation', 'est_publie', 'motif_refus', 'valide_par', 'valide_le'])
    audit_log(request, 'refus_quiz', cible=objet, details=profil.details(objet, motif=motif))
    _envoyer(f"{profil.nom_majuscule} à revoir : {objet.titre}", [
        "Bonjour,", "",
        f"Votre {profil.nom} « {objet.titre} » n'a pas été validé par {_nom(request.user)}.",
        f"Motif : {motif}",
        "Vous pouvez le corriger puis le soumettre de nouveau.",
        "", "L'équipe PEL",
    ], [objet.cree_par])
