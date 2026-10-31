"""Exécuteur Docker : le code de l'étudiant ne s'exécute que dans des conteneurs jetables isolés.

Déroulement d'une exécution :

1. Les fichiers sont écrits dans `<dossier>/code` sur l'hôte. `<dossier>` (créé par mkdtemp) est en 0700 :
   aucun autre utilisateur local ne peut le traverser ; le démon Docker, qui fait le montage, n'en a pas
   besoin. `code` est en 0755 et ses fichiers en 0644 parce que l'utilisateur nobody du conteneur doit les
   lire (il ne traverse pas le dossier parent : le montage pointe directement sur `code`). Monté en lecture
   seule sur /code.
2. Langage compilé : un volume Docker tmpfs de 64 Mo (`docker volume create`, appartenant à nobody, jamais
   écrit sur le disque de l'hôte) reçoit le résultat de la compilation, qui porte sur tous les fichiers source
   de l'exercice (`langages.commande_compilation`). La compilation tourne dans un
   conteneur à part, de courte durée, avec sa propre mémoire max(limite de l'exercice, 512 Mo) : javac et
   g++ ne sont pas soumis à la limite de l'exercice, qui reste appliquée telle quelle à chaque test. Le
   volume y est monté en écriture sur /build, et en lecture seule dans le conteneur des tests.
   Ordre obligatoire : volume, PUIS conteneur des tests, PUIS compilation. Le pilote `local` monte un volume
   tmpfs au premier conteneur qui l'utilise et le démonte (contenu perdu) quand plus aucun ne l'utilise :
   le conteneur des tests, démarré avant, garde le binaire compilé en vie après la fin de la compilation.
3. `docker run -d` démarre le conteneur des tests, qui ne fait que dormir (`sleep`, gardé par `--init`)
   sous l'utilisateur 65533 ; chaque test est un `docker exec -i --user 65534:65534` avec l'entrée sur stdin,
   sous `timeout -s KILL` à l'intérieur du conteneur. Avant chaque test sauf le premier, `kill -9 -1` lancé
   en tant que 65534 tue tous les processus laissés par le test précédent (processus d'arrière-plan,
   `setsid`, fork bomb) sans toucher au gardien (autre uid) ni à l'init, puis /tmp est vidé. Si ce
   nettoyage ne peut pas s'exécuter alors que le conteneur tourne (fork bomb : quota de 64 processus plein),
   un nouveau conteneur des tests est démarré (il garde le volume monté) et l'ancien est supprimé avec tous
   ses processus : une fork bomb donne au pire des TLE, jamais une panne du service.
   Les tests publics passent avant les tests cachés (executeur.py) : un état laissé dans /tmp ou dans
   l'espace IPC privé par un test caché ne peut jamais réapparaître dans la sortie visible d'un test public.
4. Options de sécurité des deux conteneurs : `--log-driver none` (rien n'est journalisé sur le disque de
   l'hôte, la sortie attachée reste lue et bornée par l'exécuteur), pas de réseau, pas d'IPC partagé ni de /dev/shm
   (`--ipc none`), mémoire et mémoire d'échange égales, 1 processeur, 64 processus, système de fichiers en
   lecture seule sauf /tmp (tmpfs de 64 Mo), aucune capacité, pas d'élévation de privilèges, `--pull never`.
   Les images viennent de la configuration (PEL_IMAGES_EXECUTION) et sont de confiance : une image qui
   déclare un VOLUME créerait un volume anonyme inscriptible ; il ne faut pas en configurer.
5. `docker rm -f` des conteneurs et `docker volume rm -f` du volume dans un `finally` ; le dossier est
   effacé. Les restes d'un worker mort sont supprimés par `nettoyer_orphelins()` (étiquette `pel.fin`).

Durée bornée : une exécution dispose d'un budget global calculé (démarrage, compilation, puis pour chaque
test sa limite plus une marge), plafonné à DUREE_MAX_S (4 minutes, sous les 5 minutes de la reprise des
exécutions bloquées). Chaque appel au client docker a un délai côté hôte borné par ce budget. Un test
interrompu par l'épuisement du budget et les tests restants (non lancés) sont des dépassements de temps
(TLE) : le budget couvre toujours la limite de chaque test, il ne s'épuise donc que si le programme dépasse
ses limites ou si l'exercice cumule plus de 4 minutes de tests. Le conteneur est alors tué par `rm -f`.
Un processus d'arrière-plan qui garde la sortie ouverte ne bloque pas le test : le démon Docker rend la main
environ 2 s après la fin du processus principal (code de celui-ci, sortie gardée), et le fils est tué par le
nettoyage suivant. Un `docker exec` qui ne rend quand même pas la main est coupé côté hôte ; si le conteneur
répond encore, le test est un TLE.

Statuts : code 124, ou 137 avec un temps mesuré au moins égal à la limite : TLE ; code 137 avec
`State.OOMKilled` : MLE ; autre 137 (SIGKILL envoyé par le programme lui-même) : erreur d'exécution.
Java : « java.lang.OutOfMemoryError » avec un code non nul : MLE.

Les arguments sont toujours des listes (jamais de shell sur l'hôte) ; les sorties lues sont bornées à 64 Ko.
"""
import glob
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

from . import TAILLE_MAX_SORTIE, ServiceIndisponible, tronquer
from . import langages

logger = logging.getLogger('programming.execution')

DELAI_COMPILATION_S = 30          # délai de la compilation, dans le conteneur
MARGE_HOTE_S = 10                 # délai côté hôte d'un exec = délai dans le conteneur + cette marge
MARGE_TEST_S = 2                  # part du budget global par test, en plus de sa limite
DELAI_COMMANDE_S = 30             # run -d, volume create, inspect, nettoyage des processus
DELAI_NETTOYAGE_S = 10            # rm -f et volume rm du finally
MARGE_ETIQUETTE_S = 120           # pel.fin = début + budget + cette marge (pire cas du finally, sauts d'horloge)
DUREE_MAX_S = 240                 # plafond absolu du budget d'une exécution
AGE_ORPHELIN_S = 600              # au-delà, un dossier pel-exec-* de l'hôte est un reste
MEMOIRE_COMPILATION_MO = 512
TAILLE_TMPFS = '64m'
UTILISATEUR = '65534:65534'       # compilation et tests
UTILISATEUR_GARDIEN = '65533:65533'  # init et sleep du conteneur des tests : hors d'atteinte de kill -9 -1
ETIQUETTE = 'pel.execution=1'
ETIQUETTE_FIN = 'pel.fin'         # instant (secondes epoch) après lequel l'objet est un reste
# Constante, aucune donnée de l'étudiant : tue les processus de 65534 et vide /tmp entre deux tests.
NETTOYAGE_PROCESSUS = 'kill -9 -1 2>/dev/null; rm -rf /tmp/* /tmp/.[!.]* /tmp/..?* 2>/dev/null; exit 0'
CODES_A_VERIFIER = (125, 126, 127, 137)
MESSAGE_NON_LANCE = "Test non lancé : la durée totale de l'exécution est épuisée."
MESSAGE_COUPE = "Le programme ne s'est pas terminé dans le délai."


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
    """Octets lus -> texte enregistrable (UTF-8 avec remplacement, sans NUL, borné)."""
    return tronquer(octets[:TAILLE_MAX_SORTIE].decode('utf-8', errors='replace'))


def _secondes(limite_temps_ms):
    return f'{limite_temps_ms / 1000:g}'


def _binaire():
    return getattr(settings, 'PEL_DOCKER', None) or 'docker'


def budget_s(compile, nombre_tests, limite_temps_ms):
    """Durée maximale d'une exécution, en secondes : démarrage, compilation, tests ; au plus DUREE_MAX_S."""
    total = DELAI_COMMANDE_S + nombre_tests * (limite_temps_ms / 1000 + MARGE_TEST_S)
    if compile:
        total += DELAI_COMMANDE_S + DELAI_COMPILATION_S + MARGE_HOTE_S
    return min(DUREE_MAX_S, total)


def _commande(args, delai_s, entree=None):
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
        code = proc.wait(timeout=max(0.1, delai_s))
    except subprocess.TimeoutExpired:
        # Le client docker est tué : ses tubes se ferment, même si un processus du conteneur garde
        # sa sortie ouverte. Le processus du conteneur, lui, est tué par le nettoyage ou par rm -f.
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


def _options_isolement(memoire_mo):
    memoire = f'{int(memoire_mo)}m'
    return [
        '--log-driver', 'none',
        '--network', 'none',
        '--ipc', 'none',
        '--memory', memoire, '--memory-swap', memoire,
        '--cpus', '1',
        '--pids-limit', '64',
        '--read-only',
        '--tmpfs', f'/tmp:rw,exec,size={TAILLE_TMPFS}',
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges',
    ]


class ExecuteurDocker:
    def __init__(self):
        self.binaire = _binaire()

    def _commande(self, args, delai_s, entree=None):
        return _commande(args, delai_s, entree=entree)

    # Commandes -------------------------------------------------------------------------------

    def _etiquettes(self, fin):
        return ['--label', ETIQUETTE, '--label', f'{ETIQUETTE_FIN}={int(fin)}']

    def commande_volume(self, volume, fin):
        return [self.binaire, 'volume', 'create', '--driver', 'local', *self._etiquettes(fin),
                '--opt', 'type=tmpfs', '--opt', 'device=tmpfs',
                '--opt', f'o=size={TAILLE_TMPFS},uid=65534,gid=65534,mode=0700,nosuid,nodev',
                volume]

    def commande_compilation(self, nom, dossier, volume, image, limite_memoire_mo, compilation, fin):
        return [
            self.binaire, 'run', '--rm', '--name', nom, *self._etiquettes(fin), '--pull', 'never', '--init',
            *_options_isolement(max(int(limite_memoire_mo), MEMOIRE_COMPILATION_MO)),
            '--user', UTILISATEUR,
            '--mount', f'type=bind,source={dossier},target=/code,readonly',
            '--mount', f'type=volume,source={volume},target={langages.DOSSIER_COMPILATION},volume-nocopy',
            '--workdir', '/code',
            '--env', 'HOME=/tmp',
            '--entrypoint', 'timeout',
            image, '-s', 'KILL', str(DELAI_COMPILATION_S), *compilation,
        ]

    def commande_demarrage(self, nom, dossier, image, limite_memoire_mo, duree_s, fin, volume=None):
        montage_build = (['--mount', f'type=volume,source={volume},target={langages.DOSSIER_COMPILATION},readonly']
                         if volume else [])
        return [
            self.binaire, 'run', '-d', '--rm', '--name', nom, *self._etiquettes(fin), '--pull', 'never', '--init',
            *_options_isolement(limite_memoire_mo),
            '--user', UTILISATEUR_GARDIEN,
            '--mount', f'type=bind,source={dossier},target=/code,readonly',
            *montage_build,
            '--workdir', '/code',
            '--env', 'HOME=/tmp',
            '--entrypoint', 'sleep',
            image, str(duree_s),
        ]

    def commande_test(self, nom, lancement, limite_temps_ms):
        return [self.binaire, 'exec', '-i', '--user', UTILISATEUR, nom,
                'timeout', '-s', 'KILL', _secondes(limite_temps_ms), *lancement]

    def commande_nettoyage(self, nom):
        return [self.binaire, 'exec', '--user', UTILISATEUR, nom, 'sh', '-c', NETTOYAGE_PROCESSUS]

    def _etat(self, nom, delai_s):
        s = self._commande([self.binaire, 'inspect', '--format', '{{json .State}}', nom], delai_s)
        if s.bloque or s.code != 0:
            raise ServiceIndisponible(f"docker inspect en échec : {_texte(s.erreurs)}")
        try:
            etat = json.loads(s.sortie.decode('utf-8', errors='replace') or '{}')
        except ValueError as erreur:
            raise ServiceIndisponible("Réponse de docker inspect illisible.") from erreur
        return bool(etat.get('Running')), bool(etat.get('OOMKilled'))

    def _supprimer(self, nom, delai_s=DELAI_NETTOYAGE_S):
        try:
            s = self._commande([self.binaire, 'rm', '-f', nom], delai_s)
            return not s.bloque and s.code == 0
        except Exception as erreur:  # noqa: BLE001 : la suppression ne doit jamais masquer l'erreur d'origine
            logger.warning("Suppression du conteneur %s impossible : %s", nom, erreur)
            return False

    def _supprimer_volume(self, volume):
        try:
            self._commande([self.binaire, 'volume', 'rm', '-f', volume], DELAI_NETTOYAGE_S)
        except Exception as erreur:  # noqa: BLE001
            logger.warning("Suppression du volume %s impossible : %s", volume, erreur)

    # Exécution ---------------------------------------------------------------------------------

    def _ecrire_fichiers(self, dossier, fichiers):
        os.chmod(dossier, 0o755)  # le dossier monté doit être lisible par l'utilisateur nobody du conteneur
        for fichier in fichiers:
            chemin = os.path.join(dossier, fichier['nom'])
            if os.path.dirname(os.path.abspath(chemin)) != os.path.abspath(dossier):
                raise langages.FichierInvalide(f"Nom de fichier refusé : {fichier['nom']!r}")
            with open(chemin, 'w', encoding='utf-8', newline='') as f:
                f.write(fichier.get('contenu') or '')
            os.chmod(chemin, 0o644)

    def lancer(self, langage, fichiers, cas, limite_temps_ms, limite_memoire_mo):
        langages.valider_noms(fichiers)
        image = langages.image(langage)
        lancement = langages.commande_lancement(langage, limite_memoire_mo)
        commande_compilation = langages.commande_compilation(langage, fichiers)
        nom = f'pel-exec-{uuid.uuid4().hex}'
        volume = f'{nom}-build' if commande_compilation else None
        budget = budget_s(bool(commande_compilation), len(cas), limite_temps_ms)
        echeance = time.monotonic() + budget
        fin = time.time() + budget + MARGE_ETIQUETTE_S
        duree_s = math.ceil(budget + 2 * DELAI_NETTOYAGE_S)
        conteneurs = []
        racine = tempfile.mkdtemp(prefix='pel-exec-', dir=getattr(settings, 'PEL_DOSSIER_EXECUTION', None) or None)
        try:
            os.chmod(racine, 0o700)
            dossier = os.path.join(racine, 'code')
            os.mkdir(dossier)
            if ',' in dossier:
                raise ServiceIndisponible(f"Dossier temporaire inutilisable pour un montage : {dossier}")
            self._ecrire_fichiers(dossier, fichiers)

            def reste():
                return echeance - time.monotonic()

            def delai(normal):
                r = reste()
                if r <= 0:
                    raise ServiceIndisponible("Durée de l'exécution épuisée avant les tests.")
                return min(normal, r)

            def demarrer(nom_gardien):
                conteneurs.append(nom_gardien)
                s = self._commande(self.commande_demarrage(nom_gardien, dossier, image, limite_memoire_mo, duree_s,
                                                           fin, volume), delai(DELAI_COMMANDE_S))
                if s.bloque or s.code != 0:
                    raise ServiceIndisponible(f"Démarrage du conteneur en échec : {_texte(s.erreurs)}")
                return nom_gardien

            if commande_compilation:
                s = self._commande(self.commande_volume(volume, fin), delai(DELAI_COMMANDE_S))
                if s.bloque or s.code != 0:
                    raise ServiceIndisponible(f"Création du volume de compilation en échec : {_texte(s.erreurs)}")
            # Le conteneur des tests démarre AVANT la compilation : il garde le volume tmpfs monté (le pilote
            # local démonte un volume tmpfs, et perd son contenu, quand plus aucun conteneur ne l'utilise).
            demarrer(nom)

            compilation = ''
            if commande_compilation:
                conteneurs.append(f'{nom}-c')
                s = self._commande(self.commande_compilation(f'{nom}-c', dossier, volume, image, limite_memoire_mo,
                                                             commande_compilation, fin),
                                   delai(DELAI_COMMANDE_S + DELAI_COMPILATION_S + MARGE_HOTE_S))
                if s.bloque:
                    raise ServiceIndisponible("Le client docker ne répond plus pendant la compilation.")
                if s.code in (125, 126, 127):
                    raise ServiceIndisponible(f"Compilation impossible (code {s.code}) : {_texte(s.erreurs)}")
                compilation = _texte(s.sortie + s.erreurs)
                if s.code != 0:
                    if s.code in (124, 137):
                        compilation = (compilation + "\nLa compilation a dépassé le délai ou la mémoire autorisés."
                                       ).strip()
                    return {'compilation_ok': False, 'compilation': compilation, 'resultats': []}

            resultats = self._tests(nom, langage, lancement, cas, limite_temps_ms, reste, demarrer, conteneurs)
            return {'compilation_ok': True, 'compilation': compilation, 'resultats': resultats}
        finally:
            for conteneur in reversed(conteneurs):
                self._supprimer(conteneur)
            if volume:
                self._supprimer_volume(volume)
            shutil.rmtree(racine, ignore_errors=True)

    def _tests(self, nom, langage, lancement, cas, limite_temps_ms, reste, demarrer, conteneurs):
        resultats = []
        perdu = epuise = False
        limite_s = limite_temps_ms / 1000
        base, remplacements = nom, 0
        for numero, un_cas in enumerate(cas):
            if perdu:
                resultats.append(self._resultat(137, 0, b'', b'', memoire=True))
                continue
            if not epuise and numero > 0:
                etat = self._nettoyer_processus(nom, reste)
                if etat == 'remplacer':
                    # Nettoyage impossible alors que le conteneur tourne (fork bomb : quota de processus plein).
                    # Un nouveau gardien prend le relais (il garde le volume de compilation monté), puis l'ancien
                    # conteneur est supprimé avec tous ses processus. Jamais une panne du service.
                    remplacements += 1
                    if reste() < 1:
                        etat = 'epuise'
                    else:
                        ancien, nom = nom, demarrer(f'{base}-r{remplacements}')
                        if self._supprimer(ancien, min(DELAI_NETTOYAGE_S, max(1, reste()))):
                            conteneurs.remove(ancien)
                        etat = 'ok'
                epuise = etat == 'epuise'
                if etat == 'perdu':
                    perdu = True
                    resultats.append(self._resultat(137, 0, b'', b'', memoire=True))
                    continue
            if epuise or reste() < 1:
                epuise = True
                resultats.append(self._resultat(None, 0, b'', MESSAGE_NON_LANCE.encode(), delai=True))
                continue
            entree = (un_cas.get('entree') or '').encode('utf-8')
            s = self._commande(self.commande_test(nom, lancement, limite_temps_ms),
                               min(limite_s + MARGE_HOTE_S, reste()), entree=entree)
            oom = False
            if s.bloque:
                logger.warning("docker exec coupé côté hôte pour un test du conteneur %s", nom)
                if reste() < 1:
                    epuise = True
                else:
                    en_marche, oom = self._etat(nom, min(DELAI_COMMANDE_S, reste()))
                    if not en_marche:
                        if not oom:
                            raise ServiceIndisponible("Le conteneur s'est arrêté pendant un test.")
                        perdu = True
                        resultats.append(self._resultat(137, s.temps_ms, s.sortie, s.erreurs, memoire=True))
                        continue
                r = self._resultat(s.code, s.temps_ms, s.sortie, s.erreurs, delai=True)
                place = TAILLE_MAX_SORTIE - len(MESSAGE_COUPE) - 1  # le message survit à la troncature
                r['erreurs'] = (r['erreurs'][:place] + '\n' + MESSAGE_COUPE).lstrip('\n')
                resultats.append(r)
                continue
            if s.code in CODES_A_VERIFIER:
                en_marche, oom = self._etat(nom, min(DELAI_COMMANDE_S, max(1, reste())))
                if not en_marche:
                    if not oom:
                        raise ServiceIndisponible("Le conteneur s'est arrêté pendant un test.")
                    perdu = True
            delai_depasse = s.code == 124 or (s.code == 137 and s.temps_ms >= limite_temps_ms)
            # SIGKILL hors délai : MLE seulement si Docker confirme une mise à mort faute de mémoire ;
            # sinon le programme s'est tué lui-même (erreur d'exécution).
            memoire = not delai_depasse and s.code == 137 and oom
            if (langage == 'java' and s.code not in (0, None) and not delai_depasse
                    and (b'java.lang.OutOfMemoryError' in s.erreurs or b'java.lang.OutOfMemoryError' in s.sortie)):
                memoire = True
            resultats.append(self._resultat(s.code, s.temps_ms, s.sortie, s.erreurs, delai=delai_depasse,
                                            memoire=memoire))
        return resultats

    def _nettoyer_processus(self, nom, reste):
        """Tue les processus du test précédent et vide /tmp. Renvoie 'ok', 'epuise', 'perdu' ou 'remplacer'."""
        if reste() < 1:
            return 'epuise'
        s = self._commande(self.commande_nettoyage(nom), min(DELAI_COMMANDE_S, reste()))
        if s.bloque and reste() < 1:
            return 'epuise'
        if s.bloque or s.code != 0:
            # inspect lève ServiceIndisponible si le démon ne répond plus : seule vraie panne du service.
            en_marche, oom = self._etat(nom, min(DELAI_COMMANDE_S, max(1, reste())))
            if not en_marche:
                if oom:
                    return 'perdu'
                raise ServiceIndisponible("Le conteneur s'est arrêté entre deux tests.")
            logger.warning("Nettoyage impossible dans %s (code %s) : conteneur remplacé", nom, s.code)
            return 'remplacer'
        return 'ok'

    @staticmethod
    def _resultat(code, temps_ms, sortie, erreurs, delai=False, memoire=False, service=False):
        return {'code_sortie': code if code is not None else -1, 'temps_ms': max(0, int(temps_ms)),
                'sortie': _texte(sortie), 'erreurs': _texte(erreurs), 'delai_depasse': delai,
                'memoire_depassee': memoire, 'erreur_service': service}


def _fin_depassee(valeur, maintenant):
    try:
        return int(valeur) < maintenant
    except (TypeError, ValueError):
        return True  # étiquette absente ou illisible : objet d'une version précédente, donc un reste


def nettoyer_orphelins():
    """Supprime les conteneurs, volumes et dossiers laissés par un worker mort. À appeler au démarrage du worker.

    Seuls les objets étiquetés `pel.execution=1` dont l'échéance `pel.fin` est passée sont supprimés : les
    exécutions en cours d'autres workers ne sont pas touchées. Ne lève jamais (Docker absent : journalisé).
    Renvoie {'conteneurs': n, 'volumes': n, 'dossiers': n}.
    """
    binaire = _binaire()
    maintenant = time.time()
    bilan = {'conteneurs': 0, 'volumes': 0, 'dossiers': 0}
    listes = [
        ('conteneurs', [binaire, 'ps', '-a', '--filter', f'label={ETIQUETTE}',
                        '--format', '{{.ID}} {{.Label "%s"}}' % ETIQUETTE_FIN], ['rm', '-f']),
        ('volumes', [binaire, 'volume', 'ls', '--filter', f'label={ETIQUETTE}',
                     '--format', '{{.Name}} {{.Label "%s"}}' % ETIQUETTE_FIN], ['volume', 'rm', '-f']),
    ]
    for cle, commande, suppression in listes:
        try:
            s = _commande(commande, DELAI_COMMANDE_S)
            if s.bloque or s.code != 0:
                logger.warning("Liste des %s Docker impossible : %s", cle, _texte(s.erreurs))
                continue
            for ligne in s.sortie.decode('utf-8', errors='replace').splitlines():
                morceaux = ligne.split()
                if not morceaux or not _fin_depassee(morceaux[1] if len(morceaux) > 1 else None, maintenant):
                    continue
                r = _commande([binaire, *suppression, morceaux[0]], DELAI_NETTOYAGE_S)
                if not r.bloque and r.code == 0:
                    bilan[cle] += 1
        except ServiceIndisponible as erreur:
            logger.warning("Nettoyage des %s Docker impossible : %s", cle, erreur)
    racine = getattr(settings, 'PEL_DOSSIER_EXECUTION', None) or tempfile.gettempdir()
    for chemin in glob.glob(os.path.join(racine, 'pel-exec-*')):
        try:
            if os.path.isdir(chemin) and not os.path.islink(chemin) \
                    and os.path.getmtime(chemin) < maintenant - AGE_ORPHELIN_S:
                shutil.rmtree(chemin)
                bilan['dossiers'] += 1
        except OSError as erreur:
            logger.warning("Suppression du dossier %s impossible : %s", chemin, erreur)
    return bilan
