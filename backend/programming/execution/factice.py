"""Exécuteur factice pour les tests : ne lance jamais le code, simule un comportement.

Le comportement est piloté par des marqueurs dans le fichier principal du langage (à défaut, le premier
fichier), placés n'importe où, par exemple dans un commentaire `# PEL:CE` ou `// PEL:CE` :

- `PEL:INDISPONIBLE` : lève ServiceIndisponible (Docker absent ou en panne) ;
- `PEL:CE` : compilation en échec (« Erreur de compilation simulée. »), aucun résultat ;
- `PEL:TLE` : chaque test dépasse le délai (code 137) ;
- `PEL:MLE` : chaque test dépasse la mémoire (code 137) ;
- `PEL:RE` : chaque test se termine avec le code 1 et « Erreur simulée. » sur la sortie d'erreur ;
- `PEL:SORTIE=texte` : chaque test affiche `texte` (`\\n` y est lu comme un saut de ligne) ;
- sinon : chaque test renvoie son entrée telle quelle sur la sortie standard.
"""
from . import ServiceIndisponible
from . import langages


class ExecuteurFactice:
    def lancer(self, langage, fichiers, cas, limite_temps_ms, limite_memoire_mo):
        config = langages.langage(langage)
        langages.valider_noms(fichiers)
        principal = next((f for f in fichiers if f['nom'] == config.fichier_principal), fichiers[0] if fichiers else None)
        contenu = (principal or {}).get('contenu') or ''
        if 'PEL:INDISPONIBLE' in contenu:
            raise ServiceIndisponible("Indisponibilité simulée.")
        if 'PEL:CE' in contenu:
            return {'compilation_ok': False, 'compilation': "Erreur de compilation simulée.", 'resultats': []}
        sortie_fixee = None
        for ligne in contenu.splitlines():
            if 'PEL:SORTIE=' in ligne:
                sortie_fixee = ligne.split('PEL:SORTIE=', 1)[1].replace('\\n', '\n')
                break
        resultats = []
        for un_cas in cas:
            r = {'code_sortie': 0, 'temps_ms': 1, 'sortie': '', 'erreurs': '', 'delai_depasse': False,
                 'memoire_depassee': False, 'erreur_service': False}
            if 'PEL:TLE' in contenu:
                r.update(code_sortie=137, temps_ms=limite_temps_ms, delai_depasse=True)
            elif 'PEL:MLE' in contenu:
                r.update(code_sortie=137, memoire_depassee=True)
            elif 'PEL:RE' in contenu:
                r.update(code_sortie=1, erreurs="Erreur simulée.")
            else:
                r['sortie'] = sortie_fixee if sortie_fixee is not None else (un_cas.get('entree') or '')
            resultats.append(r)
        return {'compilation_ok': True, 'compilation': '', 'resultats': resultats}
