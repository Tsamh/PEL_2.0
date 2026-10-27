"""Validation avant publication des devoirs : profil du module générique `quiz.validation`."""
from decimal import Decimal

from quiz.validation import Profil

from .models import Devoir

MESSAGE_PUBLICATION = "La publication de ce devoir demande la validation du responsable de formation."
CHAMPS_CONTENU = ('titre', 'objectifs', 'consignes', 'ressources', 'langage')


def _decimal(valeur):
    return str(Decimal(str(valeur)).quantize(Decimal('0.01')))


def _ordonnes(elements):
    """Éléments soumis dans l'ordre où ils seront enregistrés (ordre fourni, sinon leur rang)."""
    rangs = [(e.get('ordre', i + 1), i, e) for i, e in enumerate(elements)]
    return [e for _, _, e in sorted(rangs, key=lambda r: (r[0], r[1]))]


def _pk(objet):
    return objet if isinstance(objet, int) else objet.pk


def contenu_exercice(data):
    """Contenu comparable d'un exercice, depuis les données validées (dict) ou un objet `Exercice`."""
    if isinstance(data, dict):
        lire = data.get
        tests = _ordonnes(data.get('tests', []))
        competences = data.get('competences', [])
    else:
        def lire(cle, defaut=None):
            return getattr(data, cle)
        tests = [
            {'entree': t.entree, 'sortie_attendue': t.sortie_attendue, 'public': t.public, 'poids': t.poids}
            for t in data.tests.all()
        ]
        competences = list(data.competences.all())
    return {
        'titre': lire('titre', ''),
        'enonce': lire('enonce', ''),
        'contraintes': lire('contraintes', ''),
        'exemples': lire('exemples', []),
        'fichiers_initiaux': lire('fichiers_initiaux', []),
        'solution': lire('solution', []),
        'points': _decimal(lire('points', Decimal('1'))),
        'difficulte': lire('difficulte', 'moyen'),
        'limite_temps_ms': lire('limite_temps_ms', 2000),
        'limite_memoire_mo': lire('limite_memoire_mo', 256),
        'competences': sorted(_pk(c) for c in competences),
        'tests': [
            {'entree': t.get('entree', ''), 'sortie_attendue': t.get('sortie_attendue', ''),
             'public': bool(t.get('public', False)), 'poids': t.get('poids', 1)}
            for t in tests
        ],
    }


def exercices_modifies(devoir, exercices):
    """Vrai si la liste d'exercices soumise diffère, par son contenu, des exercices actuels du devoir."""
    actuels = devoir.exercices.prefetch_related('tests', 'competences').order_by('ordre', 'id')
    return [contenu_exercice(e) for e in actuels] != [contenu_exercice(e) for e in _ordonnes(exercices)]


def contenu_modifie(instance, attrs):
    """Vrai si la requête change le contenu du devoir (champs de contenu ou exercices, comparés par contenu)."""
    if instance is None:
        return False
    if any(cle in attrs and attrs[cle] != getattr(instance, cle) for cle in CHAMPS_CONTENU):
        return True
    return 'exercices' in attrs and exercices_modifies(instance, attrs['exercices'])


def _a_des_exercices(devoir):
    return devoir.exercices.exists()


PROFIL_DEVOIR = Profil(
    nom='devoir',
    article='ce devoir',
    message_publication=MESSAGE_PUBLICATION,
    contenu_modifie=contenu_modifie,
    a_du_contenu=_a_des_exercices,
    message_sans_contenu="Ajoutez au moins un exercice avant de soumettre le devoir.",
    url_validation='/validation-quiz',
    modele=Devoir,
)
