"""Exécuteur Docker : le code de l'étudiant ne s'exécute que dans un conteneur jetable isolé.

Déroulement d'une exécution (un conteneur par exécution) :

1. Les fichiers sont écrits dans un dossier temporaire de l'hôte, monté en lecture seule sur /code.
2. `docker run -d` démarre un conteneur qui ne fait que dormir (`sleep`), avec toutes les options de
   sécurité : pas de réseau, mémoire et mémoire d'échange égales à la limite, 1 processeur, 64 processus,
   système de fichiers en lecture seule sauf /tmp (tmpfs de 64 Mo, exécution permise pour les binaires
   compilés), aucune capacité, pas d'élévation de privilèges, utilisateur nobody (65534:65534).
3. `docker exec` compile une fois (sortie dans /tmp, qui persiste entre la compilation et les tests),
   puis lance chaque test avec l'entrée sur stdin, sous `timeout -s KILL` à l'intérieur du conteneur.
4. `docker rm -f` supprime le conteneur dans un `finally`, quoi qu'il arrive ; le dossier est effacé.

Chaque appel au client docker a aussi un délai côté hôte : un client bloqué ne bloque pas le worker.
Les arguments sont toujours des listes (jamais de shell) ; les sorties lues sont bornées à 64 Ko.
"""
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass

from django.conf import settings

from . import TAILLE_MAX_SORTIE, ServiceIndisponible
from . import langages

logger = logging.getLogger('programming.execution')

DELAI_COMPILATION_S = 30
MARGE_HOTE_S = 10
DELAI_COMMANDE_S = 60
CODES_A_VERIFIER = (125, 126, 127, 137)


@dataclass
class Sortie:
    code: int | None
    sortie: bytes
    erreurs: bytes
    temps_ms: int
    bloque: bool


def _lire(flux, tampon):
    """Lit tout le flux mais n'en garde que TAILLE_MAX_SORTIE octets (mémoire bornée)."""
    try:
        while True:
            morceau = flux.read(65536)
            if not morceau:
                break
            reste = TAILLE_MAX_SORTIE - len(tampon)
            if reste > 0:
                tampon.extend(morceau[:reste])
    except (OSError, ValueError):
        pass
    finally:
        try:
            flux.close()
        except OSError:
            pass


def _ecrire(flux, donnees):
    try:
        if donnees:
            flux.write(donnees)
    except (OSError, ValueError):
        pass
    finally:
        try:
            flux.close()
        except OSError:
            pass


def _texte(octets):
    return octets[:TAILLE_MAX_SORTIE].decode('utf-8', errors='replace')


def _secondes(limite_temps_ms):
    return f'{limite_temps_ms / 1000:g}'


class ExecuteurDocker:
    def __init__(self):
        self.binaire = getattr(settings, 'PEL_DOCKER', None) or 'docker'

    # Appels au client docker -------------------------------------------------------------------

    def _commande(self, args, delai_s, entree=None):
        debut = time.monotonic()
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE if entree is not None else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as erreur:
            raise ServiceIndisponible(f"Client docker introuvable : {erreur}") from erreur
        sortie, erreurs = bytearray(), bytearray()
        fils = [threading.Thread(target=_lire, args=(proc.stdout, sortie), daemon=True),
                threading.Thread(target=_lire, args=(proc.stderr, erreurs), daemon=True)]
        if entree is not None:
            fils.append(threading.Thread(target=_ecrire, args=(proc.stdin, entree), daemon=True))
        for fil in fils:
            fil.start()
        bloque = False
        try:
            code = proc.wait(timeout=delai_s)
        except subprocess.TimeoutExpired:
            bloque = True
            proc.kill()
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                code = None
        temps_ms = int((time.monotonic() - debut) * 1000)
        for fil in fils:
            fil.join(timeout=5)
        return Sortie(code, bytes(sortie), bytes(erreurs), temps_ms, bloque)

    def commande_demarrage(self, nom, dossier, image, limite_memoire_mo, duree_s):
        memoire = f'{int(limite_memoire_mo)}m'
        return [
            self.binaire, 'run', '-d', '--rm', '--name', nom, '--label', 'pel.execution=1', '--pull', 'never',
            '--init',
            '--network', 'none',
            '--memory', memoire, '--memory-swap', memoire,
            '--cpus', '1',
            '--pids-limit', '64',
            '--read-only',
            '--tmpfs', '/tmp:rw,exec,size=64m',
            '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges',
            '--user', '65534:65534',
            '--mount', f'type=bind,source={dossier},target=/code,readonly',
            '--workdir', '/code',
            '--env', 'HOME=/tmp',
            '--entrypoint', 'sleep',
            image, str(duree_s),
        ]

    def commande_compilation(self, nom, compilation):
        return [self.binaire, 'exec', nom, 'timeout', '-s', 'KILL', str(DELAI_COMPILATION_S), *compilation]

    def commande_test(self, nom, lancement, limite_temps_ms):
        return [self.binaire, 'exec', '-i', nom, 'timeout', '-s', 'KILL', _secondes(limite_temps_ms), *lancement]

    def _etat(self, nom):
        s = self._commande([self.binaire, 'inspect', '--format', '{{json .State}}', nom], DELAI_COMMANDE_S)
        if s.bloque or s.code != 0:
            raise ServiceIndisponible(f"docker inspect en échec : {_texte(s.erreurs)}")
        try:
            etat = json.loads(s.sortie.decode('utf-8', errors='replace') or '{}')
        except ValueError as erreur:
            raise ServiceIndisponible("Réponse de docker inspect illisible.") from erreur
        return bool(etat.get('Running')), bool(etat.get('OOMKilled'))

    def _supprimer(self, nom):
        try:
            self._commande([self.binaire, 'rm', '-f', nom], DELAI_COMMANDE_S)
        except Exception as erreur:  # noqa: BLE001 : la suppression ne doit jamais masquer l'erreur d'origine
            logger.warning("Suppression du conteneur %s impossible : %s", nom, erreur)

    # Exécution ---------------------------------------------------------------------------------

    def _ecrire_fichiers(self, dossier, fichiers):
        os.chmod(dossier, 0o755)  # lisible par l'utilisateur nobody du conteneur
        for fichier in fichiers:
            chemin = os.path.join(dossier, fichier['nom'])
            if os.path.dirname(os.path.abspath(chemin)) != os.path.abspath(dossier):
                raise langages.FichierInvalide(f"Nom de fichier refusé : {fichier['nom']!r}")
            with open(chemin, 'w', encoding='utf-8', newline='') as f:
                f.write(fichier.get('contenu') or '')
            os.chmod(chemin, 0o644)

    def lancer(self, langage, fichiers, cas, limite_temps_ms, limite_memoire_mo):
        config = langages.langage(langage)
        langages.valider_noms(fichiers)
        image = langages.image(langage)
        lancement = langages.commande_lancement(langage, limite_memoire_mo)
        nom = f'pel-exec-{uuid.uuid4().hex}'
        duree_s = math.ceil(DELAI_COMPILATION_S + MARGE_HOTE_S
                            + len(cas) * (limite_temps_ms / 1000 + MARGE_HOTE_S) + DELAI_COMMANDE_S)
        dossier = tempfile.mkdtemp(prefix='pel-exec-', dir=getattr(settings, 'PEL_DOSSIER_EXECUTION', None) or None)
        try:
            if ',' in dossier:
                raise ServiceIndisponible(f"Dossier temporaire inutilisable pour un montage : {dossier}")
            self._ecrire_fichiers(dossier, fichiers)
            s = self._commande(self.commande_demarrage(nom, dossier, image, limite_memoire_mo, duree_s),
                               DELAI_COMMANDE_S)
            if s.bloque or s.code != 0:
                raise ServiceIndisponible(f"Démarrage du conteneur en échec : {_texte(s.erreurs)}")

            compilation = ''
            if config.compilation:
                s = self._commande(self.commande_compilation(nom, config.compilation),
                                   DELAI_COMPILATION_S + MARGE_HOTE_S)
                if s.bloque:
                    raise ServiceIndisponible("Le client docker ne répond plus pendant la compilation.")
                if s.code in CODES_A_VERIFIER:
                    en_marche, _ = self._etat(nom)
                    if not en_marche:
                        raise ServiceIndisponible("Le conteneur s'est arrêté pendant la compilation.")
                compilation = _texte(s.sortie + s.erreurs)
                if s.code != 0:
                    if s.code in (124, 137):
                        compilation = (compilation + "\nLa compilation a dépassé le délai ou la mémoire autorisés."
                                       ).strip()
                    return {'compilation_ok': False, 'compilation': compilation, 'resultats': []}

            resultats = []
            conteneur_perdu = False
            for un_cas in cas:
                if conteneur_perdu:
                    resultats.append(self._resultat(137, 0, b'', b'', memoire=True))
                    continue
                entree = (un_cas.get('entree') or '').encode('utf-8')
                s = self._commande(self.commande_test(nom, lancement, limite_temps_ms),
                                   limite_temps_ms / 1000 + MARGE_HOTE_S, entree=entree)
                if s.bloque:
                    logger.error("Client docker bloqué pendant un test du conteneur %s", nom)
                    resultats.append(self._resultat(s.code, s.temps_ms, s.sortie, s.erreurs, service=True))
                    continue
                oom = False
                if s.code in CODES_A_VERIFIER:
                    en_marche, oom = self._etat(nom)
                    if not en_marche:
                        if not oom:
                            raise ServiceIndisponible("Le conteneur s'est arrêté pendant un test.")
                        conteneur_perdu = True
                delai = s.code == 124 or (s.code == 137 and s.temps_ms >= limite_temps_ms)
                # Code 137 hors délai : processus tué par le noyau faute de mémoire (OOMKilled confirmé par
                # docker inspect quand il est disponible ; ce drapeau reste levé, il ne sert donc pas seul).
                memoire = not delai and s.code == 137
                if (langage == 'java' and s.code not in (0, None) and not delai
                        and (b'java.lang.OutOfMemoryError' in s.erreurs or b'java.lang.OutOfMemoryError' in s.sortie)):
                    memoire = True
                resultats.append(self._resultat(s.code, s.temps_ms, s.sortie, s.erreurs, delai=delai, memoire=memoire))
            return {'compilation_ok': True, 'compilation': compilation, 'resultats': resultats}
        finally:
            self._supprimer(nom)
            shutil.rmtree(dossier, ignore_errors=True)

    @staticmethod
    def _resultat(code, temps_ms, sortie, erreurs, delai=False, memoire=False, service=False):
        return {'code_sortie': code if code is not None else -1, 'temps_ms': max(0, int(temps_ms)),
                'sortie': _texte(sortie), 'erreurs': _texte(erreurs), 'delai_depasse': delai,
                'memoire_depassee': memoire, 'erreur_service': service}
