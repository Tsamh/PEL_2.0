"""Langages pris en charge : image, fichier principal, compilation et lancement.

La compilation écrit dans /build, un tmpfs de taille bornée inscriptible seulement pendant la compilation,
puis monté en lecture seule pour les tests (voir docker.py).
"""
from dataclasses import dataclass

from django.conf import settings

from . import FichierInvalide

IMAGES_PAR_DEFAUT = {
    'python': 'python:3.12-alpine',
    'javascript': 'node:20-alpine',
    'c': 'gcc:13',
    'cpp': 'gcc:13',
    'java': 'eclipse-temurin:21-jdk',
}

DOSSIER_COMPILATION = '/build'
LONGUEUR_MAX_NOM = 100
# Séparateurs de chemin, caractères refusés par Windows et caractères de contrôle : la validation ne dépend
# pas du système de l'hôte.
CARACTERES_INTERDITS = frozenset('/\\:*?"<>|\x7f') | frozenset(chr(i) for i in range(32))
# Noms réservés de Windows, avec ou sans extension (`CON`, `nul.txt`, `Com1.c`), quelle que soit la casse.
NOMS_RESERVES = frozenset({'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{i}' for i in range(1, 10)}
                          | {f'LPT{i}' for i in range(1, 10)})


@dataclass(frozen=True)
class Langage:
    cle: str
    fichier_principal: str
    compilation: tuple | None
    lancement: tuple


LANGAGES = {
    'python': Langage('python', 'main.py', None, ('python3', '-B', 'main.py')),
    'javascript': Langage('javascript', 'main.js', None, ('node', 'main.js')),
    'c': Langage('c', 'main.c', ('gcc', '-O2', '-o', '/build/prog', 'main.c', '-lm'), ('/build/prog',)),
    'cpp': Langage('cpp', 'main.cpp', ('g++', '-O2', '-o', '/build/prog', 'main.cpp'), ('/build/prog',)),
    'java': Langage('java', 'Main.java', ('javac', '-d', '/build', 'Main.java'), ('java', '-cp', '/build', 'Main')),
}


def langage(cle):
    try:
        return LANGAGES[cle]
    except KeyError:
        raise ValueError(f"Langage non pris en charge : {cle}") from None


def fichier_principal(cle):
    """Nom du fichier principal du langage, ou None s'il n'est pas exécutable (`autre`)."""
    return LANGAGES[cle].fichier_principal if cle in LANGAGES else None


def message_principal(cle, fichiers):
    """Message d'erreur si le fichier principal (nom exact) manque pour un langage exécutable, sinon None."""
    principal = fichier_principal(cle)
    if principal is None or any(isinstance(f, dict) and f.get('nom') == principal for f in fichiers):
        return None
    return f"Le fichier principal {principal} est obligatoire."


def image(cle):
    langage(cle)
    images = getattr(settings, 'PEL_IMAGES_EXECUTION', None) or {}
    return images.get(cle) or IMAGES_PAR_DEFAUT[cle]


def tas_java_mo(limite_memoire_mo):
    """Tas maximal de la JVM : la limite moins une marge pour la mémoire hors tas (au moins la moitié, 8 Mo minimum).

    Un dépassement du tas fait sortir la JVM (`ExitOnOutOfMemoryError`), ce qui est lu comme MLE ;
    un dépassement de la limite du conteneur est tué par le noyau (code 137 avec OOMKilled), lu aussi comme MLE.
    """
    return max(8, limite_memoire_mo // 2, limite_memoire_mo - 64)


def commande_lancement(cle, limite_memoire_mo):
    config = langage(cle)
    if cle == 'java':
        return ['java', f'-Xmx{tas_java_mo(limite_memoire_mo)}m', '-XX:+UseSerialGC', '-XX:TieredStopAtLevel=1',
                '-XX:+ExitOnOutOfMemoryError', '-XX:-UsePerfData', '-cp', DOSSIER_COMPILATION, 'Main']
    return list(config.lancement)


def nom_refuse(nom):
    """Vrai si `nom` ne peut pas être un nom de fichier simple, sous Linux comme sous Windows.

    Refusés : vide ou trop long, fait seulement de points (`.`, `..`), séparateur de chemin, caractère de
    contrôle ou interdit par Windows, point ou espace final (`main.py.` recouvrirait `main.py` sous Windows),
    nom réservé de Windows avec ou sans extension. `a..b.py` est accepté : sans séparateur de chemin, `..`
    n'est un composant de chemin que s'il forme le nom entier.
    """
    if not isinstance(nom, str) or not nom or len(nom) > LONGUEUR_MAX_NOM:
        return True
    if set(nom) == {'.'} or nom[-1] in '. ':
        return True
    if any(c in CARACTERES_INTERDITS for c in nom):
        return True
    return nom.split('.', 1)[0].rstrip(' ').upper() in NOMS_RESERVES


def valider_noms(fichiers):
    """Refuse un nom refusé par `nom_refuse` ou en double (sans tenir compte de la casse). Lève FichierInvalide."""
    noms = set()
    for fichier in fichiers:
        nom = fichier.get('nom') if isinstance(fichier, dict) else None
        if nom_refuse(nom):
            raise FichierInvalide(f"Nom de fichier refusé : {nom!r}")
        if nom.casefold() in noms:
            raise FichierInvalide(f"Deux fichiers portent le nom {nom}.")
        if not isinstance(fichier.get('contenu', ''), str):
            raise FichierInvalide(f"Le contenu du fichier {nom} doit être un texte.")
        noms.add(nom.casefold())


def probleme_fichiers(cle, fichiers):
    """Message à afficher en compilation si les fichiers ne peuvent pas être exécutés, sinon None."""
    try:
        valider_noms(fichiers)
    except FichierInvalide as erreur:
        return str(erreur)
    principal = langage(cle).fichier_principal
    if not any(f['nom'] == principal for f in fichiers):
        return f"Le fichier principal {principal} est absent."
    return None
