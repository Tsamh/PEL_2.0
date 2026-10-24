"""Banque de questions : visibilité, contenu versionné, tags et filtres."""
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Max, Q

from accounts.permissions import ADMIN, ENSEIGNANT, RESPONSABLE, SUPERADMIN
from accounts.scoping import en_entier

from .models import QuestionBanque, TagQuestion, VersionQuestion

CHAMPS_CONTENU = ('texte', 'type_question', 'points', 'mode_notation', 'penalite', 'explication')
ENTIER_MAX = 2 ** 63 - 1


def q_banque_visible(user):
    """Q des fiches visibles : les siennes, celles partagées dans ses matières, tout l'établissement pour la gestion."""
    if user.role == SUPERADMIN:
        return Q()
    if user.role in (ADMIN, RESPONSABLE):
        return Q(etablissement_id=user.etablissement_id) if user.etablissement_id else Q(pk__in=[])
    if user.role == ENSEIGNANT:
        from referentiel.models import EnseignantMatiere
        matieres = EnseignantMatiere.objects.filter(enseignant=user).values('ec_id')
        if not user.etablissement_id:
            return Q(auteur=user)
        return Q(auteur=user) | Q(partagee=True, etablissement_id=user.etablissement_id, ec_id__in=matieres)
    return Q(pk__in=[])


def peut_modifier(user, fiche):
    if user.role == SUPERADMIN:
        return True
    if user.role in (ADMIN, RESPONSABLE):
        return bool(user.etablissement_id) and fiche.etablissement_id == user.etablissement_id
    return fiche.auteur_id == user.pk


def _decimal(valeur):
    return str(Decimal(str(valeur)).quantize(Decimal('0.01')))


def contenu_normalise(data):
    """Contenu comparable et sérialisable en JSON (décimaux en chaîne à 2 décimales)."""
    return {
        'texte': data['texte'],
        'type_question': data['type_question'],
        'points': _decimal(data['points']),
        'mode_notation': data['mode_notation'],
        'penalite': _decimal(data['penalite']),
        'explication': data['explication'],
        'choix': [
            {'texte': c['texte'], 'est_correct': bool(c['est_correct']), 'points': _decimal(c['points'])}
            for c in data['choix']
        ],
    }


def contenu_version(version):
    return contenu_normalise({**{cle: getattr(version, cle) for cle in CHAMPS_CONTENU}, 'choix': version.choix})


def contenu_question(question):
    choix = [{'texte': c.texte, 'est_correct': c.est_correct, 'points': c.points} for c in question.choix.all()]
    return contenu_normalise({**{cle: getattr(question, cle) for cle in CHAMPS_CONTENU}, 'choix': choix})


def creer_version(fiche, contenu, acteur):
    """Crée la version suivante si le contenu diffère de la version courante ; renvoie (version, créée)."""
    contenu = contenu_normalise(contenu)
    with transaction.atomic():
        QuestionBanque.objects.select_for_update().filter(pk=fiche.pk).first()
        courante = fiche.versions.order_by('-numero').first()
        if courante is not None and contenu_version(courante) == contenu:
            return courante, False
        version = VersionQuestion.objects.create(
            question=fiche, numero=(courante.numero + 1) if courante else 1, creee_par=acteur,
            **{cle: contenu[cle] for cle in CHAMPS_CONTENU}, choix=contenu['choix'],
        )
    return version, True


def appliquer_tags(fiche, chapitres, competences):
    """Remplace les tags de la fiche ; les libellés sont créés au besoin dans son établissement (sans doublon de casse)."""
    tags = []
    for type_tag, libelles in ((TagQuestion.CHAPITRE, chapitres), (TagQuestion.COMPETENCE, competences)):
        for libelle in libelles:
            libelle = ' '.join(libelle.split())[:100]
            if not libelle:
                continue
            tag = TagQuestion.objects.filter(
                etablissement_id=fiche.etablissement_id, type=type_tag, libelle__iexact=libelle,
            ).first()
            if tag is None:
                tag = TagQuestion.objects.create(etablissement_id=fiche.etablissement_id, type=type_tag, libelle=libelle)
            tags.append(tag)
    fiche.tags.set(tags)


def _identifiant(valeur):
    entier = en_entier(valeur)
    return entier if entier is not None and 1 <= entier <= ENTIER_MAX else None


def filtrer_banque(qs, params, user):
    """Filtres de la liste : archivage, matière, type, difficulté, tags (tous exigés), recherche, mes questions."""
    qs = qs.filter(archivee=params.get('archivee') == '1')
    ec = _identifiant(params.get('ec'))
    if ec is not None:
        qs = qs.filter(ec_id=ec)
    if params.get('difficulte'):
        qs = qs.filter(difficulte=params['difficulte'])
    for valeur in params.getlist('tag'):
        tag = _identifiant(valeur)
        if tag is not None:
            qs = qs.filter(tags__id=tag)
    if params.get('mes_questions') == '1':
        qs = qs.filter(auteur=user)
    courantes = VersionQuestion.objects.annotate(dernier=Max('question__versions__numero')).filter(numero=F('dernier'))
    filtre_version = False
    if params.get('type_question'):
        courantes = courantes.filter(type_question=params['type_question'])
        filtre_version = True
    recherche = (params.get('recherche') or '').strip()
    if recherche:
        courantes = courantes.filter(texte__icontains=recherche)
        filtre_version = True
    if filtre_version:
        qs = qs.filter(pk__in=courantes.values('question_id'))
    return qs
