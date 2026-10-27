"""Moteur d'exécution (sous-projet 4b) : comparaison, statuts, exécuteur Docker simulé, exécuteur factice."""
import math
import os
import stat
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from accounts.testing import build_world
from programming.execution import (
    MESSAGE_INDISPONIBLE, TAILLE_MAX_SORTIE, FichierInvalide, ServiceIndisponible, texte_stockable, tronquer,
)
from programming.execution import docker as module_docker
from programming.execution.comparaison import sorties_egales
from programming.execution.docker import ExecuteurDocker, budget_s, nettoyer_orphelins
from programming.execution.executeur import executer, obtenir_executeur, statut_du_resultat
from programming.execution.factice import ExecuteurFactice
from programming.execution.langages import LANGAGES, commande_lancement, valider_noms
from programming.models import CasDeTest, Devoir, Execution, Exercice, ReponseExercice, ResultatTest, SoumissionDevoir


def brut(code=0, sortie='', erreurs='', delai=False, memoire=False, service=False, temps=5):
    return {'code_sortie': code, 'temps_ms': temps, 'sortie': sortie, 'erreurs': erreurs,
            'delai_depasse': delai, 'memoire_depassee': memoire, 'erreur_service': service}


class ComparaisonTests(SimpleTestCase):
    def test_identiques(self):
        self.assertTrue(sorties_egales('3\n', '3\n'))

    def test_espaces_de_fin_de_ligne(self):
        self.assertTrue(sorties_egales('1 2   \n3\t\n', '1 2\n3\n'))

    def test_lignes_vides_finales(self):
        self.assertTrue(sorties_egales('3\n\n\n', '3'))
        self.assertTrue(sorties_egales('', '\n\n'))

    def test_retour_chariot(self):
        self.assertTrue(sorties_egales('a\r\nb\r\n', 'a\nb'))

    def test_casse_differente(self):
        self.assertFalse(sorties_egales('Oui', 'oui'))

    def test_espaces_de_debut_comptent(self):
        self.assertFalse(sorties_egales(' 3', '3'))

    def test_ligne_vide_interne_compte(self):
        self.assertFalse(sorties_egales('a\n\nb', 'a\nb'))

    def test_contenu_different(self):
        self.assertFalse(sorties_egales('4', '3'))


class StatutTests(SimpleTestCase):
    def test_compilation(self):
        self.assertEqual(statut_du_resultat(False, None, '3'), 'CE')
        self.assertEqual(statut_du_resultat(False, brut(sortie='3'), '3'), 'CE')

    def test_delai(self):
        self.assertEqual(statut_du_resultat(True, brut(code=137, delai=True, memoire=True), '3'), 'TLE')

    def test_memoire(self):
        self.assertEqual(statut_du_resultat(True, brut(code=137, memoire=True), '3'), 'MLE')

    def test_erreur_execution(self):
        self.assertEqual(statut_du_resultat(True, brut(code=1, sortie='3'), '3'), 'RE')

    def test_mauvaise_reponse(self):
        self.assertEqual(statut_du_resultat(True, brut(sortie='4'), '3'), 'WA')

    def test_accepte(self):
        self.assertEqual(statut_du_resultat(True, brut(sortie='3  \n\n'), '3'), 'OK')

    def test_essai_run_sans_attendue(self):
        self.assertEqual(statut_du_resultat(True, brut(sortie='nimporte'), None), 'OK')
        self.assertEqual(statut_du_resultat(True, brut(code=2), None), 'RE')

    def test_erreur_service(self):
        self.assertEqual(statut_du_resultat(True, brut(service=True), '3'), 'SE')
        self.assertEqual(statut_du_resultat(True, None, '3'), 'SE')


class LangagesTests(SimpleTestCase):
    def test_fichiers_principaux(self):
        self.assertEqual({k: v.fichier_principal for k, v in LANGAGES.items()},
                         {'python': 'main.py', 'javascript': 'main.js', 'c': 'main.c', 'cpp': 'main.cpp',
                          'java': 'Main.java'})

    def test_compilations(self):
        self.assertIsNone(LANGAGES['python'].compilation)
        self.assertIsNone(LANGAGES['javascript'].compilation)
        self.assertEqual(LANGAGES['c'].compilation, ('gcc', '-O2', '-o', '/build/prog', 'main.c', '-lm'))
        self.assertEqual(LANGAGES['cpp'].compilation, ('g++', '-O2', '-o', '/build/prog', 'main.cpp'))
        self.assertEqual(LANGAGES['java'].compilation, ('javac', '-d', '/build', 'Main.java'))

    def test_lancements(self):
        self.assertEqual(commande_lancement('python', 256), ['python3', '-B', 'main.py'])
        self.assertEqual(commande_lancement('javascript', 256), ['node', 'main.js'])
        self.assertEqual(commande_lancement('c', 256), ['/build/prog'])
        self.assertEqual(commande_lancement('cpp', 256), ['/build/prog'])
        self.assertEqual(commande_lancement('java', 256),
                         ['java', '-Xmx192m', '-XX:+UseSerialGC', '-XX:TieredStopAtLevel=1',
                          '-XX:+ExitOnOutOfMemoryError', '-XX:-UsePerfData', '-cp', '/build', 'Main'])
        self.assertIn('-Xmx32m', commande_lancement('java', 64))
        self.assertIn('-Xmx8m', commande_lancement('java', 16))

    def test_noms_refuses(self):
        for nom in ['../x.py', 'a/b.py', 'a\\b.py', '', '.', '..', '...', 'c:x.py', 'a\x00.py', '/etc/passwd',
                    'CON', 'con', 'nul.txt', 'Com1.c', 'LPT9', 'aux.tar.gz', 'PRN.py', 'main.py.', 'main.py ',
                    'a\x01.py', 'a\nb.py', 'a*b.py', 'a?.py', 'a<b>.py', 'a|b.py', 'a"b.py', 'x' * 101, None, 3]:
            with self.subTest(nom=nom), self.assertRaises(FichierInvalide):
                valider_noms([{'nom': nom, 'contenu': ''}])

    def test_doublon_refuse(self):
        with self.assertRaises(FichierInvalide):
            valider_noms([{'nom': 'main.py', 'contenu': ''}, {'nom': 'main.py', 'contenu': ''}])
        with self.assertRaises(FichierInvalide):
            valider_noms([{'nom': 'Main.java', 'contenu': ''}, {'nom': 'main.java', 'contenu': ''}])

    def test_noms_acceptes(self):
        valider_noms([{'nom': n, 'contenu': ''} for n in
                      ['main.py', 'outils_2.py', 'a..b.py', '.config', 'console.py', 'COM10.py', 'nulle.c',
                       'x' * 100]])

    def test_tronquer(self):
        self.assertEqual(tronquer('abc'), 'abc')
        self.assertEqual(tronquer(None), '')
        self.assertEqual(len(tronquer('x' * (TAILLE_MAX_SORTIE + 10))), TAILLE_MAX_SORTIE)

    def test_tronquer_retire_ce_que_postgresql_refuse(self):
        self.assertEqual(tronquer('a\x00b'), 'a\ufffdb')
        self.assertEqual(tronquer('x\ud800y'), 'x\ufffdy')
        self.assertEqual(texte_stockable('\x00' * 3), '\ufffd' * 3)


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def genre(args):
    """Nature d'un appel au client docker simulé."""
    sous = args[1]
    if sous == 'volume':
        return {'create': 'volume', 'rm': 'volume_rm', 'ls': 'volume_ls'}[args[2]]
    if sous == 'run':
        return 'demarrage' if args[2] == '-d' else 'compilation'
    if sous == 'exec':
        return 'nettoyage' if 'sh' in args else 'test'
    return sous


class FauxProcessus:
    """Remplace subprocess.Popen : répond selon la sous-commande docker demandée et fait avancer l'horloge."""

    def __init__(self, scenario, horloge):
        self.scenario = scenario
        self.horloge = horloge
        self.appels = []
        self.delais = []
        self.entrees = []

    def __call__(self, args, **kwargs):
        args = list(args)
        self.appels.append(args)
        reponse = self.scenario(args)
        code, sortie, erreurs = reponse[:3]
        duree = reponse[3] if len(reponse) > 3 else 0.01
        return _Processus(self, args, code, sortie, erreurs, duree)

    def de_genre(self, nature):
        return [a for a in self.appels if genre(a) == nature]


class _Entree:
    def __init__(self, faux):
        self.faux = faux

    def write(self, donnees):
        self.faux.entrees.append(bytes(donnees))

    def close(self):
        pass


class _Processus:
    def __init__(self, faux, args, code, sortie, erreurs, duree):
        if isinstance(code, Exception):
            raise code
        self.faux, self.args = faux, args
        self.returncode = None
        self._code, self._duree = code, duree
        self.stdin = _Entree(faux)
        self.stdout = _Flux(sortie)
        self.stderr = _Flux(erreurs)

    def wait(self, timeout=None):
        if self.returncode is not None:
            return self.returncode
        self.faux.delais.append((genre(self.args), timeout))
        if self._code == 'bloque' or (timeout is not None and self._duree > timeout):
            self.faux.horloge.t += timeout
            raise subprocess.TimeoutExpired('docker', timeout)
        self.faux.horloge.t += self._duree
        self.returncode = self._code
        return self.returncode

    def kill(self):
        self.returncode = -9


class _Flux:
    def __init__(self, donnees):
        self._donnees = donnees

    def read(self, taille=-1):
        donnees, self._donnees = self._donnees, b''
        return donnees

    def close(self):
        pass


EN_MARCHE = b'{"Running":true,"OOMKilled":false}'


def scenario_normal(sorties=None, compilation=(0, b'', b''), exec_code=0, inspect=EN_MARCHE, nettoyage=(0, b'', b'')):
    sorties = list(sorties or [])
    inspections = list(inspect) if isinstance(inspect, list) else None

    def repondre(args):
        nature = genre(args)
        if nature == 'demarrage':
            return 0, b'abc123\n', b''
        if nature in ('rm', 'volume', 'volume_rm'):
            return 0, b'', b''
        if nature == 'inspect':
            if inspections is not None:
                return inspections.pop(0)
            return 0, inspect, b''
        if nature == 'compilation':
            return compilation
        if nature == 'nettoyage':
            return nettoyage
        if nature == 'test':
            if sorties:
                return sorties.pop(0)
            return exec_code, b'', b''
        raise AssertionError(args)
    return repondre


class ExecuteurDockerTests(SimpleTestCase):
    FICHIERS_C = [{'nom': 'main.c', 'contenu': 'int main(){return 0;}'}]
    FICHIERS_PY = [{'nom': 'main.py', 'contenu': 'print(input())'}]

    def lancer(self, scenario, langage='python', fichiers=None, cas=None, temps=2000, memoire=256):
        self.faux = FauxProcessus(scenario, Horloge())
        self.racines = []
        vrai = module_docker.tempfile.mkdtemp

        def mkdtemp(**kwargs):
            self.racines.append(vrai(**kwargs))
            return self.racines[-1]
        with mock.patch.object(module_docker.subprocess, 'Popen', self.faux), \
                mock.patch.object(module_docker.time, 'monotonic', self.faux.horloge), \
                mock.patch.object(module_docker.tempfile, 'mkdtemp', mkdtemp):
            rapport = ExecuteurDocker().lancer(langage, fichiers or self.FICHIERS_PY,
                                               cas if cas is not None else [{'entree': '1'}], temps, memoire)
        return rapport, self.faux.appels

    def commande_run(self, appels):
        return next(a for a in appels if genre(a) == 'demarrage')

    def nom(self, appels):
        run = next(a for a in appels if a[1] == 'run')
        nom = run[run.index('--name') + 1]
        return nom[:-2] if nom.endswith('-c') else nom

    def fin(self, commande):
        etiquette = next(x for x in commande if x.startswith('pel.fin='))
        return etiquette.split('=', 1)[1]

    def test_commande_de_demarrage_exacte(self):
        vus = {}

        def scenario(args):
            if genre(args) == 'demarrage':
                montage = args[args.index('--mount') + 1]
                source = montage.split('source=', 1)[1].split(',target=', 1)[0]
                vus['fichiers'] = {n: open(os.path.join(source, n), encoding='utf-8').read()
                                   for n in os.listdir(source)}
            return scenario_normal()(args)
        _, appels = self.lancer(scenario, memoire=128)
        run = self.commande_run(appels)
        nom = self.nom(appels)
        dossier = os.path.join(self.racines[0], 'code')
        self.assertTrue(self.fin(run).isdigit())
        self.assertEqual(run, [
            'docker', 'run', '-d', '--rm', '--name', nom, '--label', 'pel.execution=1',
            '--label', f'pel.fin={self.fin(run)}', '--pull', 'never', '--init',
            '--log-driver', 'none',
            '--network', 'none', '--ipc', 'none', '--memory', '128m', '--memory-swap', '128m', '--cpus', '1',
            '--pids-limit', '64', '--read-only', '--tmpfs', '/tmp:rw,exec,size=64m', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--user', '65533:65533',
            '--mount', f'type=bind,source={dossier},target=/code,readonly',
            '--workdir', '/code', '--env', 'HOME=/tmp', '--entrypoint', 'sleep', 'python:3.12-alpine',
            str(math.ceil(budget_s(False, 1, 2000) + 2 * module_docker.DELAI_NETTOYAGE_S)),
        ])
        self.assertEqual(vus['fichiers'], {'main.py': 'print(input())'})
        self.assertFalse(self.faux.de_genre('volume'))
        self.assertFalse(self.faux.de_genre('compilation'))

    def test_compilation_dans_un_conteneur_a_part(self):
        rapport, appels = self.lancer(scenario_normal(), langage='c', fichiers=self.FICHIERS_C,
                                      cas=[{'entree': ''}, {'entree': ''}], memoire=64)
        nom = self.nom(appels)
        volume = f'{nom}-build'
        dossier = os.path.join(self.racines[0], 'code')
        creation = self.faux.de_genre('volume')[0]
        self.assertEqual(creation, [
            'docker', 'volume', 'create', '--driver', 'local', '--label', 'pel.execution=1',
            '--label', f'pel.fin={self.fin(creation)}', '--opt', 'type=tmpfs', '--opt', 'device=tmpfs',
            '--opt', 'o=size=64m,uid=65534,gid=65534,mode=0700,nosuid,nodev', volume])
        compilation = self.faux.de_genre('compilation')
        self.assertEqual(len(compilation), 1)
        self.assertEqual(compilation[0], [
            'docker', 'run', '--rm', '--name', f'{nom}-c', '--label', 'pel.execution=1',
            '--label', f'pel.fin={self.fin(compilation[0])}', '--pull', 'never', '--init',
            '--log-driver', 'none',
            '--network', 'none', '--ipc', 'none', '--memory', '512m', '--memory-swap', '512m', '--cpus', '1',
            '--pids-limit', '64', '--read-only', '--tmpfs', '/tmp:rw,exec,size=64m', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--user', '65534:65534',
            '--mount', f'type=bind,source={dossier},target=/code,readonly',
            '--mount', f'type=volume,source={volume},target=/build,volume-nocopy',
            '--workdir', '/code', '--env', 'HOME=/tmp', '--entrypoint', 'timeout',
            'gcc:13', '-s', 'KILL', '30', 'gcc', '-O2', '-o', '/build/prog', 'main.c', '-lm'])
        self.assertIn(('compilation', 70), self.faux.delais)
        run = self.commande_run(appels)
        self.assertEqual(run[run.index('--memory') + 1], '64m')
        self.assertEqual(run[run.index('--memory-swap') + 1], '64m')
        i = run.index('--workdir')
        self.assertEqual(run[i - 4:i], ['--mount', f'type=bind,source={dossier},target=/code,readonly',
                                        '--mount', f'type=volume,source={volume},target=/build,readonly'])
        self.assertEqual(self.faux.de_genre('test'),
                         [['docker', 'exec', '-i', '--user', '65534:65534', nom, 'timeout', '-s', 'KILL', '2',
                           '/build/prog']] * 2)
        self.assertTrue(rapport['compilation_ok'])
        # Le conteneur des tests démarre avant la compilation : il garde le volume tmpfs (et le binaire) monté.
        self.assertEqual([genre(a) for a in appels],
                         ['volume', 'demarrage', 'compilation', 'test', 'nettoyage', 'test', 'rm', 'rm', 'volume_rm'])
        self.assertEqual(appels[-3:], [['docker', 'rm', '-f', f'{nom}-c'], ['docker', 'rm', '-f', nom],
                                       ['docker', 'volume', 'rm', '-f', volume]])

    def test_memoire_de_compilation_au_moins_la_limite(self):
        _, appels = self.lancer(scenario_normal(), langage='cpp', fichiers=[{'nom': 'main.cpp', 'contenu': ''}],
                                memoire=1024)
        compilation = self.faux.de_genre('compilation')[0]
        self.assertEqual(compilation[compilation.index('--memory') + 1], '1024m')
        self.assertEqual(compilation[-5:], ['g++', '-O2', '-o', '/build/prog', 'main.cpp'])

    def test_lancement_par_test_entree_et_nettoyage(self):
        rapport, appels = self.lancer(scenario_normal(sorties=[(0, b'1\n', b''), (0, b'2\n', b'')]),
                                      cas=[{'entree': '1'}, {'entree': 'é'}], temps=1500)
        nom = self.nom(appels)
        test = ['docker', 'exec', '-i', '--user', '65534:65534', nom, 'timeout', '-s', 'KILL', '1.5',
                'python3', '-B', 'main.py']
        nettoyage = ['docker', 'exec', '--user', '65534:65534', nom, 'sh', '-c',
                     'kill -9 -1 2>/dev/null; rm -rf /tmp/* /tmp/.[!.]* /tmp/..?* 2>/dev/null; exit 0']
        execs = [a for a in appels if a[1] == 'exec']
        self.assertEqual(execs, [test, nettoyage, test])
        self.assertEqual(self.faux.entrees, [b'1', 'é'.encode('utf-8')])
        self.assertEqual([d for g, d in self.faux.delais if g == 'test'], [11.5, 11.5])
        self.assertTrue(rapport['compilation_ok'])
        self.assertEqual([r['sortie'] for r in rapport['resultats']], ['1\n', '2\n'])
        self.assertEqual(rapport['resultats'][0]['code_sortie'], 0)

    def test_compilation_en_echec(self):
        rapport, appels = self.lancer(scenario_normal(compilation=(1, b'', b'main.c:1: error')), langage='c',
                                      fichiers=self.FICHIERS_C)
        self.assertFalse(rapport['compilation_ok'])
        self.assertEqual(rapport['compilation'], 'main.c:1: error')
        self.assertEqual(rapport['resultats'], [])
        self.assertFalse(self.faux.de_genre('test'))
        nom = self.nom(appels)
        self.assertEqual([genre(a) for a in appels], ['volume', 'demarrage', 'compilation', 'rm', 'rm', 'volume_rm'])
        self.assertEqual(appels[-3:], [['docker', 'rm', '-f', f'{nom}-c'], ['docker', 'rm', '-f', nom],
                                       ['docker', 'volume', 'rm', '-f', f'{nom}-build']])

    def test_compilation_hors_delai_ou_memoire(self):
        for code in (124, 137):
            with self.subTest(code=code):
                rapport, _ = self.lancer(scenario_normal(compilation=(code, b'', b'')), langage='c',
                                         fichiers=self.FICHIERS_C)
                self.assertFalse(rapport['compilation_ok'])
                self.assertEqual(rapport['compilation'], "La compilation a dépassé le délai ou la mémoire autorisés.")
                self.assertFalse(self.faux.de_genre('test'))

    def test_compilation_impossible_service_indisponible(self):
        for reponse in [(125, b'', b'No such image'), (127, b'', b''), ('bloque', b'', b'')]:
            with self.subTest(reponse=reponse[0]), self.assertRaises(ServiceIndisponible):
                self.lancer(scenario_normal(compilation=reponse), langage='c', fichiers=self.FICHIERS_C)
            nom = self.nom(self.faux.appels)
            self.assertEqual(self.faux.appels[-3:], [['docker', 'rm', '-f', f'{nom}-c'], ['docker', 'rm', '-f', nom],
                                                     ['docker', 'volume', 'rm', '-f', f'{nom}-build']])

    def test_sortie_de_compilation_sans_nul(self):
        rapport, _ = self.lancer(scenario_normal(compilation=(1, b'err\x00eur', b'')), langage='c',
                                 fichiers=self.FICHIERS_C)
        self.assertEqual(rapport['compilation'], 'err\ufffdeur')

    def test_conteneur_supprime_meme_en_cas_d_exception(self):
        def scenario(args):
            if genre(args) == 'test':
                return RuntimeError('panne'), b'', b''
            return scenario_normal()(args)
        with self.assertRaises(RuntimeError):
            self.lancer(scenario)
        self.assertEqual(self.faux.appels[-1], ['docker', 'rm', '-f', self.nom(self.faux.appels)])

    def test_dossier_temporaire_supprime(self):
        self.lancer(scenario_normal())
        self.assertFalse(os.path.exists(self.racines[0]))

    @unittest.skipUnless(os.name == 'posix', "Droits POSIX")
    def test_droits_du_dossier(self):
        droits = {}

        def scenario(args):
            if genre(args) == 'demarrage':
                code = os.path.join(self.racines[0], 'code')
                droits.update(racine=stat.S_IMODE(os.stat(self.racines[0]).st_mode),
                              code=stat.S_IMODE(os.stat(code).st_mode),
                              fichier=stat.S_IMODE(os.stat(os.path.join(code, 'main.py')).st_mode))
            return scenario_normal()(args)
        self.lancer(scenario)
        self.assertEqual(droits, {'racine': 0o700, 'code': 0o755, 'fichier': 0o644})

    def test_docker_absent(self):
        def scenario(args):
            return FileNotFoundError('docker'), b'', b''
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario)

    def test_demarrage_en_echec_conteneur_supprime(self):
        def scenario(args):
            if genre(args) == 'demarrage':
                return 125, b'', b'Cannot connect to the Docker daemon'
            return 0, b'', b''
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario)
        self.assertEqual(self.faux.appels[-1], ['docker', 'rm', '-f', self.nom(self.faux.appels)])
        self.assertFalse(self.faux.de_genre('test'))

    def test_demarrage_bloque(self):
        def scenario(args):
            if genre(args) == 'demarrage':
                return 'bloque', b'', b''
            return 0, b'', b''
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario)
        self.assertEqual(self.faux.appels[-1], ['docker', 'rm', '-f', self.nom(self.faux.appels)])

    def test_nom_de_fichier_avec_chemin_refuse(self):
        with self.assertRaises(FichierInvalide):
            self.lancer(scenario_normal(), fichiers=[{'nom': '../main.py', 'contenu': ''}])

    def test_delai_depasse_code_124(self):
        rapport, _ = self.lancer(scenario_normal(exec_code=124))
        self.assertTrue(rapport['resultats'][0]['delai_depasse'])

    def test_oom(self):
        rapport, appels = self.lancer(scenario_normal(exec_code=137, inspect=b'{"Running":true,"OOMKilled":true}'))
        r = rapport['resultats'][0]
        self.assertEqual((r['memoire_depassee'], r['delai_depasse']), (True, False))
        self.assertEqual(statut_du_resultat(True, r, ''), 'MLE')
        self.assertEqual(self.faux.de_genre('inspect'),
                         [['docker', 'inspect', '--format', '{{json .State}}', self.nom(appels)]])

    def test_sigkill_sans_oom_est_une_erreur_d_execution(self):
        rapport, _ = self.lancer(scenario_normal(exec_code=137))
        r = rapport['resultats'][0]
        self.assertEqual((r['code_sortie'], r['memoire_depassee'], r['delai_depasse']), (137, False, False))
        self.assertEqual(statut_du_resultat(True, r, ''), 'RE')

    def test_code_137_apres_le_delai_est_un_depassement_de_temps(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[(137, b'', b'', 2.5)],
                                                 inspect=b'{"Running":true,"OOMKilled":true}'), temps=2000)
        self.assertTrue(rapport['resultats'][0]['delai_depasse'])
        self.assertFalse(rapport['resultats'][0]['memoire_depassee'])

    def test_conteneur_perdu_par_oom(self):
        rapport, _ = self.lancer(scenario_normal(exec_code=137, inspect=b'{"Running":false,"OOMKilled":true}'),
                                 cas=[{'entree': ''}] * 3)
        self.assertEqual([statut_du_resultat(True, r, '') for r in rapport['resultats']], ['MLE'] * 3)
        self.assertEqual(len(self.faux.de_genre('test')), 1)
        self.assertFalse(self.faux.de_genre('nettoyage'))

    def test_conteneur_arrete_sans_oom(self):
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario_normal(exec_code=137, inspect=b'{"Running":false,"OOMKilled":false}'))

    def test_erreur_execution(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[(1, b'', b'Traceback')]))
        r = rapport['resultats'][0]
        self.assertEqual((r['code_sortie'], r['erreurs'], r['delai_depasse'], r['memoire_depassee']),
                         (1, 'Traceback', False, False))

    def test_exec_qui_ne_rend_pas_la_main_est_un_depassement_de_temps(self):
        # Un processus d'arrière-plan garde la sortie ouverte : le client docker est coupé côté hôte, le
        # conteneur répond encore, le test est un TLE ; les processus restants sont tués avant le test suivant.
        rapport, appels = self.lancer(scenario_normal(sorties=[('bloque', b'', b''), (0, b'2\n', b'')]),
                                      cas=[{'entree': '1'}, {'entree': '2'}], temps=1000)
        statuts = [statut_du_resultat(True, r, a) for r, a in zip(rapport['resultats'], ['1', '2'])]
        self.assertEqual(statuts, ['TLE', 'OK'])
        self.assertIn(module_docker.MESSAGE_COUPE, rapport['resultats'][0]['erreurs'])
        self.assertEqual([g for g, _ in self.faux.delais if g in ('test', 'inspect', 'nettoyage')],
                         ['test', 'inspect', 'nettoyage', 'test'])
        self.assertEqual(self.faux.delais[[g for g, _ in self.faux.delais].index('test')], ('test', 11.0))

    def test_exec_bloque_et_docker_ne_repond_plus(self):
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario_normal(sorties=[('bloque', b'', b'')], inspect=[('bloque', b'', b'')]))

    def test_fork_bomb_nettoyage_impossible_conteneur_remplace(self):
        # Quota de processus plein : l'exec du nettoyage échoue, le conteneur tourne encore. Un nouveau
        # conteneur des tests prend le relais, l'ancien est supprimé ; aucune panne du service.
        for nettoyage in [(126, b'', b'OCI runtime exec failed: resource temporarily unavailable'),
                          ('bloque', b'', b'')]:
            with self.subTest(nettoyage=nettoyage[0]):
                rapport, appels = self.lancer(
                    scenario_normal(sorties=[('bloque', b'', b''), (0, b'2\n', b''), (0, b'3\n', b'')],
                                    nettoyage=nettoyage),
                    langage='c', fichiers=self.FICHIERS_C, cas=[{'entree': '1'}, {'entree': '2'}, {'entree': '3'}],
                    temps=1000)
                nom = self.nom(appels)
                statuts = [statut_du_resultat(True, r, a) for r, a in zip(rapport['resultats'], ['1', '2', '3'])]
                self.assertEqual(statuts, ['TLE', 'OK', 'OK'])
                demarrages = self.faux.de_genre('demarrage')
                noms = [d[d.index('--name') + 1] for d in demarrages]
                self.assertEqual(noms, [nom, f'{nom}-r1', f'{nom}-r2'])
                # le nouveau gardien remonte le volume de compilation avant la suppression de l'ancien
                self.assertTrue(all(f'type=volume,source={nom}-build,target=/build,readonly' in d
                                    for d in demarrages))
                tests = self.faux.de_genre('test')
                self.assertEqual([t[5] for t in tests], [nom, f'{nom}-r1', f'{nom}-r2'])
                sequence = [(genre(a), a[-1] if genre(a) == 'rm' else None) for a in appels
                            if genre(a) in ('demarrage', 'rm')]
                self.assertEqual(sequence, [('demarrage', None), ('demarrage', None), ('rm', nom),
                                            ('demarrage', None), ('rm', f'{nom}-r1'), ('rm', f'{nom}-r2'),
                                            ('rm', f'{nom}-c')])
                self.assertEqual(appels[-1], ['docker', 'volume', 'rm', '-f', f'{nom}-build'])

    def test_nettoyage_conteneur_arrete_sans_oom(self):
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario_normal(nettoyage=(1, b'', b''), inspect=b'{"Running":false,"OOMKilled":false}'),
                        cas=[{'entree': ''}] * 2)

    def test_message_coupe_survit_a_la_troncature(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[('bloque', b'', b'e' * (TAILLE_MAX_SORTIE * 2))]))
        erreurs = rapport['resultats'][0]['erreurs']
        self.assertTrue(erreurs.endswith(module_docker.MESSAGE_COUPE))
        self.assertLessEqual(len(erreurs), TAILLE_MAX_SORTIE)

    def test_budget(self):
        self.assertEqual(budget_s(False, 2, 1000), 30 + 2 * 3)
        self.assertEqual(budget_s(True, 1, 1000), 30 + 3 + 30 + 30 + 10)
        self.assertEqual(budget_s(True, 100, 10000), module_docker.DUREE_MAX_S)
        self.assertEqual(module_docker.DUREE_MAX_S, 240)

    def test_duree_totale_bornee_tests_restants_hors_delai(self):
        # 100 tests qui dépassent chacun leur limite de 10 s : sans budget global, plus de 1 000 s.
        def scenario(args):
            if genre(args) == 'test':
                return 124, b'', b'', 10.2
            return scenario_normal()(args)
        rapport, appels = self.lancer(scenario, cas=[{'entree': ''}] * 100, temps=10000)
        resultats = rapport['resultats']
        self.assertEqual(len(resultats), 100)
        self.assertEqual({statut_du_resultat(True, r, '') for r in resultats}, {'TLE'})
        lances = len(self.faux.de_genre('test'))
        self.assertLess(lances, 30)
        self.assertEqual([r['erreurs'] for r in resultats[lances:]], [module_docker.MESSAGE_NON_LANCE] * (100 - lances))
        self.assertLessEqual(self.faux.horloge.t - 1000.0, module_docker.DUREE_MAX_S + 1)
        run = self.commande_run(appels)
        self.assertEqual(run[-1], str(module_docker.DUREE_MAX_S + 2 * module_docker.DELAI_NETTOYAGE_S))
        self.assertTrue(all(d <= 20 for g, d in self.faux.delais if g == 'test'))

    def test_budget_epuise_pendant_un_exec_bloque(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[('bloque', b'', b'')] * 100), cas=[{'entree': ''}] * 100,
                                 temps=10000)
        self.assertEqual({statut_du_resultat(True, r, '') for r in rapport['resultats']}, {'TLE'})
        delais_tests = [d for g, d in self.faux.delais if g == 'test']
        self.assertLess(delais_tests[-1], 20)  # dernier exec coupé à l'échéance, pas à limite + marge
        self.assertLessEqual(self.faux.horloge.t - 1000.0, module_docker.DUREE_MAX_S + 1)

    def test_java_hors_memoire(self):
        rapport, appels = self.lancer(
            scenario_normal(sorties=[(3, b'', b'Terminating due to java.lang.OutOfMemoryError: Java heap space')]),
            langage='java', fichiers=[{'nom': 'Main.java', 'contenu': 'class Main{}'}])
        self.assertTrue(rapport['resultats'][0]['memoire_depassee'])
        self.assertIn('eclipse-temurin:21-jdk', self.commande_run(appels))
        self.assertEqual(self.faux.de_genre('compilation')[0][-4:], ['javac', '-d', '/build', 'Main.java'])

    def test_sorties_tronquees(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[(0, b'x' * (TAILLE_MAX_SORTIE * 3), b'')]))
        self.assertEqual(len(rapport['resultats'][0]['sortie']), TAILLE_MAX_SORTIE)

    def test_sortie_avec_nul(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[(0, b'a\x00b', b'\x00')]))
        self.assertEqual((rapport['resultats'][0]['sortie'], rapport['resultats'][0]['erreurs']),
                         ('a\ufffdb', '\ufffd'))

    @override_settings(PEL_IMAGES_EXECUTION={'python': 'mon/python:1'})
    def test_image_surchargee(self):
        _, appels = self.lancer(scenario_normal())
        self.assertIn('mon/python:1', self.commande_run(appels))

    def test_langage_non_pris_en_charge(self):
        with self.assertRaises(ValueError):
            self.lancer(scenario_normal(), langage='autre')


class NettoyageOrphelinsTests(SimpleTestCase):
    def test_supprime_les_restes_expires(self):
        maintenant = int(time.time())
        appels = []

        def scenario(args):
            nature = genre(args)
            if nature == 'ps':
                return 0, f'aaa {maintenant - 10}\nbbb {maintenant + 600}\nccc \n'.encode(), b''
            if nature == 'volume_ls':
                return 0, f'v1 {maintenant - 10}\nv2 {maintenant + 600}\n'.encode(), b''
            return 0, b'', b''
        faux = FauxProcessus(scenario, Horloge())
        with tempfile.TemporaryDirectory() as racine:
            for nom in ('pel-exec-vieux', 'pel-exec-recent', 'autre-vieux'):
                os.mkdir(os.path.join(racine, nom))
            vieux = time.time() - module_docker.AGE_ORPHELIN_S - 60
            for nom in ('pel-exec-vieux', 'autre-vieux'):
                os.utime(os.path.join(racine, nom), (vieux, vieux))
            with override_settings(PEL_DOSSIER_EXECUTION=racine), \
                    mock.patch.object(module_docker.subprocess, 'Popen', faux):
                bilan = nettoyer_orphelins()
            self.assertEqual(sorted(os.listdir(racine)), ['autre-vieux', 'pel-exec-recent'])
        appels = faux.appels
        self.assertEqual(bilan, {'conteneurs': 2, 'volumes': 1, 'dossiers': 1})
        self.assertEqual(appels[0], ['docker', 'ps', '-a', '--filter', 'label=pel.execution=1',
                                     '--format', '{{.ID}} {{.Label "pel.fin"}}'])
        self.assertIn(['docker', 'volume', 'ls', '--filter', 'label=pel.execution=1',
                       '--format', '{{.Name}} {{.Label "pel.fin"}}'], appels)
        suppressions = [a for a in appels if genre(a) in ('rm', 'volume_rm')]
        self.assertEqual(suppressions, [['docker', 'rm', '-f', 'aaa'], ['docker', 'rm', '-f', 'ccc'],
                                        ['docker', 'volume', 'rm', '-f', 'v1']])

    def test_docker_absent_ne_leve_pas(self):
        faux = FauxProcessus(lambda args: (FileNotFoundError('docker'), b'', b''), Horloge())
        with tempfile.TemporaryDirectory() as racine, override_settings(PEL_DOSSIER_EXECUTION=racine), \
                mock.patch.object(module_docker.subprocess, 'Popen', faux), \
                self.assertLogs('programming.execution', level='WARNING'):
            self.assertEqual(nettoyer_orphelins(), {'conteneurs': 0, 'volumes': 0, 'dossiers': 0})

class ExecuteurFacticeTests(SimpleTestCase):
    def lancer(self, contenu, cas=None, langage='python'):
        nom = LANGAGES[langage].fichier_principal
        return ExecuteurFactice().lancer(langage, [{'nom': nom, 'contenu': contenu}],
                                         cas if cas is not None else [{'entree': 'abc'}], 2000, 256)

    def test_echo(self):
        rapport = self.lancer('print(input())')
        self.assertTrue(rapport['compilation_ok'])
        self.assertEqual(rapport['resultats'][0]['sortie'], 'abc')

    def test_sortie_fixee(self):
        self.assertEqual(self.lancer('# PEL:SORTIE=42\\n')['resultats'][0]['sortie'], '42\n')

    def test_marqueurs(self):
        self.assertFalse(self.lancer('# PEL:CE')['compilation_ok'])
        self.assertTrue(self.lancer('# PEL:TLE')['resultats'][0]['delai_depasse'])
        self.assertTrue(self.lancer('# PEL:MLE')['resultats'][0]['memoire_depassee'])
        self.assertEqual(self.lancer('// PEL:RE', langage='c')['resultats'][0]['code_sortie'], 1)

    def test_indisponible(self):
        with self.assertRaises(ServiceIndisponible):
            self.lancer('# PEL:INDISPONIBLE')


@override_settings(PEL_EXECUTEUR='factice')
class ExecuterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.devoir = Devoir.objects.create(titre='TP', filiere=a.filiere, langage='python', cree_par=a.ens)
        cls.exo = Exercice.objects.create(devoir=cls.devoir, titre='Somme')
        cls.public = CasDeTest.objects.create(exercice=cls.exo, ordre=0, entree='1 2', sortie_attendue='1 2',
                                              public=True)
        cls.cache = CasDeTest.objects.create(exercice=cls.exo, ordre=1, entree='40 2', sortie_attendue='42',
                                             public=False, poids=2)

    def execution(self, type_, contenu='print(input())', **extra):
        fichiers = [{'nom': 'main.py', 'contenu': contenu}]
        if type_ == Execution.CORRECTION:
            soumission = SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.w.a.etu)
            extra['reponse'] = ReponseExercice.objects.create(soumission=soumission, exercice=self.exo,
                                                              fichiers=fichiers)
            fichiers = []
        return Execution.objects.create(type=type_, demandeur=self.w.a.etu, devoir=self.devoir, exercice=self.exo,
                                        fichiers=fichiers, statut=Execution.EN_COURS, **extra)

    def test_choix_executeur(self):
        self.assertIsInstance(obtenir_executeur(), ExecuteurFactice)
        with override_settings(PEL_EXECUTEUR='docker'):
            self.assertIsInstance(obtenir_executeur(), ExecuteurDocker)

    def test_essai_test_publics_seulement(self):
        e = self.execution(Execution.ESSAI_TEST)
        executer(e)
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.TERMINEE)
        self.assertIsNotNone(e.fin)
        resultats = list(e.resultats.all())
        self.assertEqual([(r.cas_id, r.statut, r.sortie) for r in resultats], [(self.public.id, 'OK', '1 2')])

    def test_correction_tous_les_tests(self):
        e = self.execution(Execution.CORRECTION)
        executer(e)
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.TERMINEE)
        self.assertEqual([(r.cas_id, r.ordre, r.statut) for r in e.resultats.all()],
                         [(self.public.id, 0, 'OK'), (self.cache.id, 1, 'WA')])

    def test_essai_run(self):
        e = self.execution(Execution.ESSAI_RUN, entree='bonjour')
        executer(e)
        r = e.resultats.get()
        self.assertEqual((r.cas_id, r.statut, r.sortie), (None, 'OK', 'bonjour'))

    def test_compilation_en_echec(self):
        e = self.execution(Execution.CORRECTION, contenu='# PEL:CE')
        executer(e)
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.TERMINEE)
        self.assertIn('simulée', e.compilation)
        self.assertEqual([r.statut for r in e.resultats.all()], ['CE', 'CE'])

    def test_statuts(self):
        for marqueur, statut in [('TLE', 'TLE'), ('MLE', 'MLE'), ('RE', 'RE')]:
            with self.subTest(marqueur=marqueur):
                e = self.execution(Execution.ESSAI_TEST, contenu=f'# PEL:{marqueur}')
                executer(e)
                self.assertEqual(e.resultats.get().statut, statut)

    def test_service_indisponible(self):
        e = self.execution(Execution.ESSAI_TEST, contenu='# PEL:INDISPONIBLE')
        executer(e)
        e.refresh_from_db()
        self.assertEqual((e.statut, e.message), (Execution.ERREUR, MESSAGE_INDISPONIBLE))
        self.assertEqual(MESSAGE_INDISPONIBLE, "Le service d'exécution est indisponible.")
        self.assertFalse(e.resultats.exists())

    def test_panne_inattendue(self):
        e = self.execution(Execution.ESSAI_TEST)
        with mock.patch.object(ExecuteurFactice, 'lancer', side_effect=RuntimeError('boum')), \
                self.assertLogs('programming.execution', level='ERROR'):
            executer(e)
        e.refresh_from_db()
        self.assertEqual((e.statut, e.message), (Execution.ERREUR, MESSAGE_INDISPONIBLE))

    def test_fichier_principal_absent(self):
        e = Execution.objects.create(type=Execution.ESSAI_TEST, demandeur=self.w.a.etu, devoir=self.devoir,
                                     exercice=self.exo, fichiers=[{'nom': 'autre.py', 'contenu': ''}])
        executer(e)
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.TERMINEE)
        self.assertEqual(e.compilation, "Le fichier principal main.py est absent.")
        self.assertEqual(e.resultats.get().statut, 'CE')

    def test_nom_de_fichier_invalide(self):
        e = Execution.objects.create(type=Execution.ESSAI_TEST, demandeur=self.w.a.etu, devoir=self.devoir,
                                     exercice=self.exo,
                                     fichiers=[{'nom': 'main.py', 'contenu': ''}, {'nom': '../x', 'contenu': ''}])
        executer(e)
        e.refresh_from_db()
        self.assertEqual(e.resultats.get().statut, 'CE')
        self.assertIn('../x', e.compilation)

    def test_langage_non_pris_en_charge(self):
        Devoir.objects.filter(pk=self.devoir.pk).update(langage='autre')
        e = self.execution(Execution.ESSAI_TEST)
        e.devoir.refresh_from_db()
        executer(e)
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.ERREUR)
        self.assertEqual(e.message, "Ce langage n'est pas pris en charge par le service d'exécution.")

    def test_relance_remplace_les_resultats(self):
        e = self.execution(Execution.CORRECTION)
        executer(e)
        executer(e)
        self.assertEqual(e.resultats.count(), 2)

    def test_sorties_tronquees(self):
        e = self.execution(Execution.ESSAI_RUN, contenu='print(input())', entree='y' * (TAILLE_MAX_SORTIE + 5))
        executer(e)
        self.assertEqual(len(e.resultats.get().sortie), TAILLE_MAX_SORTIE)

    def test_aucun_test(self):
        self.exo.tests.update(public=False)
        e = self.execution(Execution.ESSAI_TEST)
        executer(e)
        e.refresh_from_db()
        self.assertEqual((e.statut, e.resultats.count()), (Execution.TERMINEE, 0))

    def test_sortie_avec_nul_enregistree(self):
        e = self.execution(Execution.ESSAI_RUN, contenu='# PEL:SORTIE=a\x00b')
        executer(e)
        r = e.resultats.get()
        self.assertEqual((r.statut, r.sortie), ('OK', 'a\ufffdb'))

    def test_enregistrement_impossible_passe_en_erreur(self):
        e = self.execution(Execution.CORRECTION)
        vrai = ResultatTest.objects.bulk_create

        def bulk_create(objets, *args, **kwargs):
            if objets:
                raise ValueError('A string literal cannot contain NUL (0x00) characters.')
            return vrai(objets, *args, **kwargs)
        with mock.patch.object(ResultatTest.objects, 'bulk_create', side_effect=bulk_create), \
                self.assertLogs('programming.execution', level='ERROR'):
            executer(e)
        e.refresh_from_db()
        self.assertEqual((e.statut, e.message), (Execution.ERREUR, MESSAGE_INDISPONIBLE))
        self.assertFalse(e.resultats.exists())
        self.assertIsNotNone(e.fin)

    def test_tests_publics_avant_les_tests_caches(self):
        exo = Exercice.objects.create(devoir=self.devoir, titre='Ordre')
        cache = CasDeTest.objects.create(exercice=exo, ordre=0, entree='c0', sortie_attendue='c0', public=False)
        public = CasDeTest.objects.create(exercice=exo, ordre=1, entree='p1', sortie_attendue='p1', public=True)
        cache2 = CasDeTest.objects.create(exercice=exo, ordre=2, entree='c2', sortie_attendue='x', public=False)
        soumission = SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.w.a.etu)
        reponse = ReponseExercice.objects.create(soumission=soumission, exercice=exo,
                                                 fichiers=[{'nom': 'main.py', 'contenu': 'print(input())'}])
        e = Execution.objects.create(type=Execution.CORRECTION, demandeur=self.w.a.etu, devoir=self.devoir,
                                     exercice=exo, reponse=reponse, statut=Execution.EN_COURS)
        vrai = ExecuteurFactice.lancer
        recus = []

        def lancer(executeur, langage, fichiers, cas, *args):
            recus.extend(c['entree'] for c in cas)
            return vrai(executeur, langage, fichiers, cas, *args)
        with mock.patch.object(ExecuteurFactice, 'lancer', lancer):
            executer(e)
        self.assertEqual(recus, ['p1', 'c0', 'c2'])
        self.assertEqual([(r.ordre, r.cas_id, r.sortie, r.statut) for r in e.resultats.order_by('ordre')],
                         [(0, cache.id, 'c0', 'OK'), (1, public.id, 'p1', 'OK'), (2, cache2.id, 'c2', 'WA')])

    def test_borne_des_tests_pour_l_enseignant(self):
        from programming.execution import BUDGET_TESTS_MS
        self.assertEqual(BUDGET_TESTS_MS, 140_000)
        self.assertLessEqual(BUDGET_TESTS_MS / 1000 + module_docker.DELAI_COMMANDE_S * 2
                             + module_docker.DELAI_COMPILATION_S + module_docker.MARGE_HOTE_S,
                             module_docker.DUREE_MAX_S)
