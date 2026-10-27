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
import re

MESSAGE_INDISPONIBLE = "Le service d'exécution est indisponible."
TAILLE_MAX_SORTIE = 64 * 1024
# Borne côté enseignant (validation de l'API, tâche 4) : nombre de tests x limite_temps_ms d'un exercice.
# Avec le plafond de 240 s d'une exécution (docker.DUREE_MAX_S), il reste environ 100 s pour le démarrage,
# la compilation et le surcoût des docker exec : un programme correct n'est jamais coupé par le budget global.
BUDGET_TESTS_MS = 140_000

# Un champ texte PostgreSQL refuse le caractère NUL ; un demi-codet UTF-16 isolé ne s'encode pas en UTF-8.
_NON_STOCKABLES = re.compile('[\x00\ud800-\udfff]')
REMPLACEMENT = '\ufffd'


class ServiceIndisponible(Exception):
    """Docker est absent, arrêté ou en panne : l'exécution passe en erreur."""


class FichierInvalide(ValueError):
    """Nom de fichier refusé (chemin, doublon, caractère interdit)."""


def texte_stockable(texte):
    """Texte enregistrable sous SQLite comme sous PostgreSQL : NUL et demi-codets deviennent U+FFFD."""
    if texte is None:
        return ''
    if not isinstance(texte, str):
        texte = str(texte)
    return _NON_STOCKABLES.sub(REMPLACEMENT, texte)


def tronquer(texte, taille=TAILLE_MAX_SORTIE):
    """Texte borné à `taille` caractères et enregistrable (voir `texte_stockable`)."""
    return texte_stockable(texte or '')[:taille]
