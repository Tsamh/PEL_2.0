"""Import et export CSV de la banque de questions (UTF-8, séparateur point-virgule)."""
import csv
import io

NB_CHOIX = 10
ENTETE = (
    ['type', 'texte', 'points', 'mode', 'penalite', 'difficulte', 'chapitres', 'competences', 'explication']
    + [f'{nom}{i}' for i in range(1, NB_CHOIX + 1) for nom in ('choix', 'correct', 'points')]
)
TAILLE_MAX = 2 * 1024 * 1024
LIGNES_MAX = 1000
DEBUTS_DANGEREUX = ('=', '+', '-', '@', '\t', '\r')
OUI, NON = 'oui', 'non'


class ErreurFichier(Exception):
    pass


def _neutraliser(valeur):
    texte = '' if valeur is None else str(valeur)
    return "'" + texte if texte.startswith(DEBUTS_DANGEREUX) else texte


def _relire(cellule):
    """Annule la neutralisation de l'export : une apostrophe suivie d'un début dangereux."""
    if cellule.startswith("'") and cellule[1:].startswith(DEBUTS_DANGEREUX):
        return cellule[1:]
    return cellule


def _ecrire(lignes):
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, delimiter=';', lineterminator='\r\n')
    ecrivain.writerow(ENTETE)
    for valeurs in lignes:
        valeurs = valeurs + [''] * (len(ENTETE) - len(valeurs))
        ecrivain.writerow([_neutraliser(v) for v in valeurs])
    return '\ufeff' + sortie.getvalue()


def exporter(fiches):
    lignes = []
    for fiche in fiches:
        version = fiche.courante
        tags = list(fiche.tags.all())
        valeurs = [
            version.type_question, version.texte, version.points, version.mode_notation, version.penalite,
            fiche.difficulte,
            '|'.join(t.libelle for t in tags if t.type == 'chapitre'),
            '|'.join(t.libelle for t in tags if t.type == 'competence'),
            version.explication,
        ]
        for choix in version.choix[:NB_CHOIX]:
            valeurs += [choix['texte'], OUI if choix['est_correct'] else NON, choix['points']]
        lignes.append(valeurs)
    return _ecrire(lignes)


def modele():
    return _ecrire([[
        'qcm', 'Combien font 2 + 2 ?', '1', 'tout_ou_rien', '0', 'facile', 'Arithmétique', 'Calcul mental',
        '2 + 2 font 4.', '4', OUI, '0', '5', NON, '0',
    ]])


def lire_lignes(fichier):
    """Lignes non vides du fichier, numérotées comme dans un tableur (l'en-tête est la ligne 1)."""
    if fichier.size > TAILLE_MAX:
        raise ErreurFichier("Le fichier dépasse 2 Mo.")
    try:
        texte = fichier.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ErreurFichier("Le fichier doit être encodé en UTF-8.")
    try:
        lignes = list(csv.reader(io.StringIO(texte, newline=''), delimiter=';'))
    except csv.Error:
        raise ErreurFichier("Le fichier CSV est mal formé.")
    if not lignes:
        raise ErreurFichier("Le fichier est vide.")
    entete = [c.strip().lower() for c in lignes[0]]
    while entete and not entete[-1]:
        entete.pop()
    if entete != ENTETE:
        raise ErreurFichier("L'en-tête du fichier ne correspond pas au modèle.")
    corps = [(numero, l) for numero, l in enumerate(lignes[1:], start=2) if any(c.strip() for c in l)]
    if not corps:
        raise ErreurFichier("Le fichier ne contient aucune question.")
    if len(corps) > LIGNES_MAX:
        raise ErreurFichier(f"Le fichier dépasse {LIGNES_MAX} lignes.")
    return [(numero, dict(zip(ENTETE, [_relire(c) for c in l] + [''] * len(ENTETE)))) for numero, l in corps]


def _nombre(texte, defaut):
    texte = texte.strip().replace(',', '.')
    return texte or defaut


def vers_donnees(ligne):
    """Corps d'API d'une ligne (même format qu'une création), et erreurs propres au CSV."""
    erreurs = []
    choix = []
    for i in range(1, NB_CHOIX + 1):
        texte = ligne[f'choix{i}'].strip()
        if not texte:
            continue
        correct = ligne[f'correct{i}'].strip().lower()
        if correct not in (OUI, NON, ''):
            erreurs.append(f"correct{i} : la valeur doit être oui ou non.")
        choix.append({'texte': texte, 'est_correct': correct == OUI, 'points': _nombre(ligne[f'points{i}'], '0')})
    donnees = {
        'difficulte': ligne['difficulte'].strip().lower() or 'moyen',
        'chapitres': [t for t in ligne['chapitres'].split('|') if t.strip()],
        'competences': [t for t in ligne['competences'].split('|') if t.strip()],
        'contenu': {
            'type_question': ligne['type'].strip().lower() or 'qcm',
            'texte': ligne['texte'].strip(),
            'points': _nombre(ligne['points'], '1'),
            'mode_notation': ligne['mode'].strip().lower() or 'tout_ou_rien',
            'penalite': _nombre(ligne['penalite'], '0'),
            'explication': ligne['explication'].strip(),
            'choix': choix,
        },
    }
    return donnees, erreurs


def aplatir(erreurs, prefixe=''):
    """Messages lisibles « champ : message » à partir des erreurs imbriquées de DRF."""
    if isinstance(erreurs, dict):
        return [m for cle, valeur in erreurs.items()
                for m in aplatir(valeur, prefixe if cle == 'non_field_errors' else cle)]
    if isinstance(erreurs, list):
        return [m for valeur in erreurs for m in aplatir(valeur, prefixe)]
    return [f'{prefixe} : {erreurs}' if prefixe else str(erreurs)]
