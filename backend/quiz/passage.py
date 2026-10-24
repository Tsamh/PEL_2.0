"""Cycle de vie d'une tentative de quiz : démarrage, réponses, soumission, expiration, visibilité."""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.scoping import en_entier
from audit.services import log as audit_log

from .correction import corriger_tentative
from .exceptions import Conflit
from .models import Quiz, ReponseQuiz, TentativeQuiz

logger = logging.getLogger(__name__)

TOLERANCE = timedelta(seconds=30)
TEXTE_MAX = 5000


def calculer_fin_prevue(quiz, debut):
    fin = debut + timedelta(minutes=quiz.duree_minutes)
    if quiz.date_fin and quiz.date_fin < fin:
        return quiz.date_fin
    return fin


def est_expiree(tentative):
    return tentative.statut == TentativeQuiz.EN_COURS and timezone.now() > tentative.fin_prevue + TOLERANCE


def reprise_possible(quiz, etudiant):
    """Vrai si demarrer reprendrait une tentative en cours au lieu d'en créer une."""
    en_cours = quiz.tentatives.filter(etudiant=etudiant, statut=TentativeQuiz.EN_COURS).first()
    return en_cours is not None and quiz.reprise_autorisee and not est_expiree(en_cours)


def demarrer(quiz, etudiant):
    """Renvoie (tentative, créée). Reprend la tentative en cours si la reprise est autorisée."""
    en_cours = quiz.tentatives.filter(etudiant=etudiant, statut=TentativeQuiz.EN_COURS).first()
    if en_cours is not None:
        if quiz.reprise_autorisee and not est_expiree(en_cours):
            return en_cours, False
        soumettre(en_cours, auto=True)

    maintenant = timezone.now()
    if quiz.date_debut and maintenant < quiz.date_debut:
        raise Conflit("Ce quiz n'est pas encore ouvert.")
    if quiz.date_fin and maintenant >= quiz.date_fin:
        raise Conflit("Ce quiz est fermé.")

    with transaction.atomic():
        # Verrou sur l'étudiant : deux démarrages simultanés ne créent pas deux tentatives.
        get_user_model().objects.select_for_update().get(pk=etudiant.pk)
        concurrente = quiz.tentatives.filter(etudiant=etudiant, statut=TentativeQuiz.EN_COURS).first()
        if concurrente is not None:
            return concurrente, False
        nombre = quiz.tentatives.filter(etudiant=etudiant).count()
        if nombre >= quiz.tentatives_autorisees:
            raise Conflit("Vous n'avez plus de tentative disponible pour ce quiz.")
        tentative = TentativeQuiz.objects.create(
            quiz=quiz, etudiant=etudiant, numero=nombre + 1,
            debut=maintenant, fin_prevue=calculer_fin_prevue(quiz, maintenant),
        )
    return tentative, True


def _refus(message):
    raise ValidationError({'detail': message})


def enregistrer_reponse(tentative, data):
    """Crée ou remplace la réponse à une question. data : {question, choix: [ids], texte}."""
    with transaction.atomic():
        tentative = TentativeQuiz.objects.select_for_update().get(pk=tentative.pk)
        if tentative.statut == TentativeQuiz.SOUMISE:
            raise Conflit("Cette tentative est déjà soumise.")
        if est_expiree(tentative):
            expiree = True
        else:
            expiree = False
            reponse = _ecrire_reponse(tentative, data)
    if expiree:
        soumettre(tentative, auto=True)
        raise Conflit("Le temps est écoulé : votre tentative a été soumise automatiquement.")
    return reponse


def _ecrire_reponse(tentative, data):
    if not isinstance(data, dict):
        _refus("La réponse doit être un objet avec les champs question, choix et texte.")
    question_id = en_entier(data.get('question'))
    question = None
    if question_id is not None:
        question = tentative.quiz.questions.prefetch_related('choix').filter(pk=question_id).first()
    if question is None:
        _refus("Cette question ne fait pas partie du quiz.")

    brut = data.get('choix', [])
    if not isinstance(brut, list):
        _refus("Le champ choix doit être une liste d'identifiants.")
    choix_ids = [en_entier(v) for v in brut]
    if None in choix_ids:
        _refus("Le champ choix doit être une liste d'identifiants.")
    choix_ids = list(dict.fromkeys(choix_ids))
    if question.type_question == 'courte' and choix_ids:
        _refus("Une question à réponse courte n'a pas de choix.")
    if not set(choix_ids) <= {c.id for c in question.choix.all()}:
        _refus("Ce choix ne fait pas partie de la question.")
    if len(choix_ids) > 1 and not question.est_multiple:
        _refus("Une seule réponse est attendue pour cette question.")

    texte = data.get('texte', '')
    if texte is None:
        texte = ''
    if not isinstance(texte, str):
        _refus("La réponse doit être un texte.")
    if len(texte) > TEXTE_MAX:
        _refus(f"La réponse ne doit pas dépasser {TEXTE_MAX} caractères.")

    reponse, _ = ReponseQuiz.objects.get_or_create(tentative=tentative, question=question)
    reponse.texte_reponse = texte if question.type_question == 'courte' else ''
    reponse.save(update_fields=['texte_reponse'])
    reponse.choix_selectionnes.set(choix_ids)
    return reponse


def soumettre(tentative, auto=False, request=None):
    """Soumet et corrige. Idempotent : sans effet (False) si la tentative est déjà soumise."""
    with transaction.atomic():
        verrouillee = TentativeQuiz.objects.select_for_update().get(pk=tentative.pk)
        if verrouillee.statut == TentativeQuiz.SOUMISE:
            soumise = False
        else:
            soumise = True
            verrouillee.statut = TentativeQuiz.SOUMISE
            verrouillee.soumise_le = min(timezone.now(), verrouillee.fin_prevue)
            verrouillee.soumission_auto = auto
            verrouillee.save(update_fields=['statut', 'soumise_le', 'soumission_auto'])
            corriger_tentative(verrouillee)
            audit_log(request, 'soumission_quiz', cible=verrouillee, acteur=verrouillee.etudiant,
                      details={'numero': verrouillee.numero, 'auto': auto, 'score': str(verrouillee.score)})
            transaction.on_commit(lambda: envoyer_accuse(verrouillee))
    tentative.refresh_from_db()
    return soumise


def cloturer_si_expiree(tentative):
    if est_expiree(tentative):
        return soumettre(tentative, auto=True)
    return False


def cloturer_expirees(queryset=None):
    """Soumet les tentatives expirées. Une erreur sur une tentative est journalisée sans arrêter le lot."""
    qs = TentativeQuiz.objects.all() if queryset is None else queryset
    limite = timezone.now() - TOLERANCE
    nombre = 0
    for tentative in qs.filter(statut=TentativeQuiz.EN_COURS, fin_prevue__lt=limite):
        try:
            if soumettre(tentative, auto=True):
                nombre += 1
        except Exception:
            logger.exception("Échec de la soumission automatique de la tentative %s", tentative.pk)
    return nombre


def envoyer_accuse(tentative):
    etudiant = tentative.etudiant
    if not etudiant.email:
        return
    quand = timezone.localtime(tentative.soumise_le).strftime('%d/%m/%Y à %H:%M')
    lignes = [
        f"Bonjour {etudiant.get_full_name() or etudiant.username},",
        "",
        f"Nous confirmons la réception de votre tentative n°{tentative.numero} au quiz « {tentative.quiz.titre} », "
        f"soumise le {quand}.",
    ]
    if tentative.soumission_auto:
        lignes.append("Elle a été soumise automatiquement à la fin du temps imparti, avec les réponses enregistrées.")
    lignes += ["", "L'équipe PEL"]
    send_mail(f"Accusé de réception : {tentative.quiz.titre}", "\n".join(lignes),
              settings.DEFAULT_FROM_EMAIL, [etudiant.email], fail_silently=True)


def score_visible(quiz):
    return quiz.publication_resultats == Quiz.PUBLICATION_IMMEDIATE or quiz.resultats_publies


def corrige_visible(tentative):
    """Le corrigé n'est montré qu'une fois que l'étudiant ne peut plus le réutiliser."""
    quiz = tentative.quiz
    if tentative.statut != TentativeQuiz.SOUMISE or not quiz.afficher_corrige or not score_visible(quiz):
        return False
    if quiz.date_fin is not None and timezone.now() >= quiz.date_fin:
        return True
    return quiz.tentatives.filter(etudiant_id=tentative.etudiant_id).count() >= quiz.tentatives_autorisees


def meilleure_tentative(tentatives):
    """Meilleure tentative soumise (à égalité, la plus ancienne), ou None."""
    soumises = [t for t in tentatives if t.statut == TentativeQuiz.SOUMISE]
    if not soumises:
        return None
    return max(soumises, key=lambda t: (t.score, -t.numero))
