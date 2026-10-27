"""Exécution isolée du code des étudiants (sous-projet 4b).

Aucun code d'étudiant n'est exécuté hors d'un conteneur Docker isolé : l'exécuteur réel est
`docker.ExecuteurDocker` ; `factice.ExecuteurFactice` ne lance jamais le code (tests seulement).

Contrat d'un exécuteur :
    lancer(langage, fichiers, cas, limite_temps_ms, limite_memoire_mo) -> Rapport
    fichiers : [{nom, contenu}] ; cas : [{entree}]
    Rapport : {compilation_ok: bool, compilation: str,
               resultats: [{code_sortie, temps_ms, sortie, erreurs, delai_depasse, memoire_depassee,
                            erreur_service}]}
    (un résultat par cas, dans l'ordre ; `resultats` vide si la compilation échoue)
    Lève ServiceIndisponible si Docker est absent ou en panne, FichierInvalide pour un nom refusé.
"""

MESSAGE_INDISPONIBLE = "Le service d'exécution est indisponible."
TAILLE_MAX_SORTIE = 64 * 1024


class ServiceIndisponible(Exception):
    """Docker est absent, arrêté ou en panne : l'exécution passe en erreur."""


class FichierInvalide(ValueError):
    """Nom de fichier refusé (chemin, doublon, caractère interdit)."""


def tronquer(texte, taille=TAILLE_MAX_SORTIE):
    texte = texte or ''
    return texte[:taille]
