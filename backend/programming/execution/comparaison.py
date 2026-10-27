"""Comparaison tolérante des sorties."""


def _lignes(texte):
    lignes = [ligne.rstrip() for ligne in (texte or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')]
    while lignes and not lignes[-1]:
        lignes.pop()
    return lignes


def sorties_egales(obtenue, attendue):
    """Égalité ligne à ligne, espaces de fin de ligne et lignes vides finales ignorés, `\\r\\n` lu comme `\\n`.

    La casse et les espaces de début de ligne comptent.
    """
    return _lignes(obtenue) == _lignes(attendue)
