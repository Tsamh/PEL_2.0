"""Langages pris en charge : image, fichier principal, compilation et lancement."""
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

CARACTERES_INTERDITS = ('/', '\\', ':', '\x00')


@dataclass(frozen=True)
class Langage:
    cle: str
    fichier_principal: str
    compilation: tuple | None
    lancement: tuple


LANGAGES = {
    'python': Langage('python', 'main.py', None, ('python3', '-B', 'main.py')),
    'javascript': Langage('javascript', 'main.js', None, ('node', 'main.js')),
    'c': Langage('c', 'main.c', ('gcc', '-O2', '-o', '/tmp/prog', 'main.c', '-lm'), ('/tmp/prog',)),
    'cpp': Langage('cpp', 'main.cpp', ('g++', '-O2', '-o', '/tmp/prog', 'main.cpp'), ('/tmp/prog',)),
    'java': Langage('java', 'Main.java', ('javac', '-d', '/tmp', 'Main.java'), ('java', '-cp', '/tmp', 'Main')),
}


def langage(cle):
    try:
        return LANGAGES[cle]
    except KeyError:
        raise ValueError(f"Langage non pris en charge : {cle}") from None


def image(cle):
    langage(cle)
    images = getattr(settings, 'PEL_IMAGES_EXECUTION', None) or {}
    return images.get(cle) or IMAGES_PAR_DEFAUT[cle]


def tas_java_mo(limite_memoire_mo):
    """Tas maximal de la JVM : la limite moins une marge pour la mémoire hors tas (au moins la moitié, 8 Mo minimum).

    Un dépassement du tas fait sortir la JVM (`ExitOnOutOfMemoryError`), ce qui est lu comme MLE ;
    un dépassement de la limite du conteneur est tué par le noyau (code 137), lu aussi comme MLE.
    """
    return max(8, limite_memoire_mo // 2, limite_memoire_mo - 64)


def commande_lancement(cle, limite_memoire_mo):
    config = langage(cle)
    if cle == 'java':
        return ['java', f'-Xmx{tas_java_mo(limite_memoire_mo)}m', '-XX:+UseSerialGC', '-XX:TieredStopAtLevel=1',
                '-XX:+ExitOnOutOfMemoryError', '-XX:-UsePerfData', '-cp', '/tmp', 'Main']
    return list(config.lancement)


def valider_noms(fichiers):
    """Refuse un nom vide, avec chemin, `.`/`..`, caractère interdit ou en double. Lève FichierInvalide."""
    noms = set()
    for fichier in fichiers:
        nom = fichier.get('nom') if isinstance(fichier, dict) else None
        if (not isinstance(nom, str) or not nom or nom in ('.', '..') or '..' in nom
                or any(c in nom for c in CARACTERES_INTERDITS) or len(nom) > 100):
            raise FichierInvalide(f"Nom de fichier refusé : {nom!r}")
        if nom in noms:
            raise FichierInvalide(f"Deux fichiers portent le nom {nom}.")
        if not isinstance(fichier.get('contenu', ''), str):
            raise FichierInvalide(f"Le contenu du fichier {nom} doit être un texte.")
        noms.add(nom)


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
