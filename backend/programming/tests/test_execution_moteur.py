"""Moteur d'exécution (sous-projet 4b) : comparaison, statuts, exécuteur Docker simulé, exécuteur factice."""
import itertools
import os
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from accounts.testing import build_world
from programming.execution import (
    MESSAGE_INDISPONIBLE, TAILLE_MAX_SORTIE, FichierInvalide, ServiceIndisponible, tronquer,
)
from programming.execution import docker as module_docker
from programming.execution.comparaison import sorties_egales
from programming.execution.docker import ExecuteurDocker
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
        self.assertEqual(LANGAGES['c'].compilation, ('gcc', '-O2', '-o', '/tmp/prog', 'main.c', '-lm'))
        self.assertEqual(LANGAGES['cpp'].compilation, ('g++', '-O2', '-o', '/tmp/prog', 'main.cpp'))
        self.assertEqual(LANGAGES['java'].compilation, ('javac', '-d', '/tmp', 'Main.java'))

    def test_lancements(self):
        self.assertEqual(commande_lancement('python', 256), ['python3', '-B', 'main.py'])
        self.assertEqual(commande_lancement('javascript', 256), ['node', 'main.js'])
        self.assertEqual(commande_lancement('c', 256), ['/tmp/prog'])
        java = commande_lancement('java', 256)
        self.assertEqual(java[0], 'java')
        self.assertEqual(java[-3:], ['-cp', '/tmp', 'Main'])
        self.assertIn('-Xmx192m', java)
        self.assertIn('-XX:+ExitOnOutOfMemoryError', java)
        self.assertIn('-Xmx32m', commande_lancement('java', 64))
        self.assertIn('-Xmx8m', commande_lancement('java', 16))

    def test_noms_refuses(self):
        for nom in ['../x.py', 'a/b.py', 'a\\b.py', '', '.', '..', 'c:x.py', 'a\x00.py', '/etc/passwd']:
            with self.subTest(nom=nom), self.assertRaises(FichierInvalide):
                valider_noms([{'nom': nom, 'contenu': ''}])

    def test_doublon_refuse(self):
        with self.assertRaises(FichierInvalide):
            valider_noms([{'nom': 'main.py', 'contenu': ''}, {'nom': 'main.py', 'contenu': ''}])

    def test_noms_acceptes(self):
        valider_noms([{'nom': 'main.py', 'contenu': ''}, {'nom': 'outils_2.py', 'contenu': ''}])

    def test_tronquer(self):
        self.assertEqual(tronquer('abc'), 'abc')
        self.assertEqual(len(tronquer('x' * (TAILLE_MAX_SORTIE + 10))), TAILLE_MAX_SORTIE)


class FauxProcessus:
    """Remplace subprocess.Popen : répond selon la sous-commande docker demandée."""

    def __init__(self, scenario, appels):
        self.scenario = scenario
        self.appels = appels

    def __call__(self, args, **kwargs):
        self.appels.append(list(args))
        code, sortie, erreurs = self.scenario(list(args))
        return _Processus(code, sortie, erreurs)


class _Processus:
    def __init__(self, code, sortie, erreurs):
        if isinstance(code, Exception):
            raise code
        self.returncode = None
        self._code = code
        self.stdin = mock.MagicMock()
        self.stdout = _Flux(sortie)
        self.stderr = _Flux(erreurs)

    def wait(self, timeout=None):
        if self._code == 'bloque':
            import subprocess
            if self.returncode is None:
                raise subprocess.TimeoutExpired('docker', timeout)
        self.returncode = -9 if self._code == 'bloque' else self._code
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


def scenario_normal(sorties=None, compilation=(0, b'', b''), exec_code=0, inspect=b'{"Running":true,"OOMKilled":false}'):
    sorties = list(sorties or [])

    def repondre(args):
        sous = args[1]
        if sous == 'run':
            return 0, b'abc123\n', b''
        if sous == 'rm':
            return 0, b'', b''
        if sous == 'inspect':
            return 0, inspect, b''
        if sous == 'exec':
            if '-i' not in args:
                return compilation
            if sorties:
                return sorties.pop(0)
            return exec_code, b'', b''
        raise AssertionError(args)
    return repondre


class ExecuteurDockerTests(SimpleTestCase):
    FICHIERS_C = [{'nom': 'main.c', 'contenu': 'int main(){return 0;}'}]
    FICHIERS_PY = [{'nom': 'main.py', 'contenu': 'print(input())'}]

    def lancer(self, scenario, langage='python', fichiers=None, cas=None, temps=2000, memoire=256):
        appels = []
        with mock.patch.object(module_docker.subprocess, 'Popen', FauxProcessus(scenario, appels)):
            rapport = ExecuteurDocker().lancer(langage, fichiers or self.FICHIERS_PY,
                                               cas if cas is not None else [{'entree': '1'}], temps, memoire)
        return rapport, appels

    def commande_run(self, appels):
        return next(a for a in appels if a[1] == 'run')

    def test_options_de_securite(self):
        _, appels = self.lancer(scenario_normal(), memoire=128)
        run = self.commande_run(appels)
        texte = ' '.join(run)
        for option in ['--network none', '--memory 128m', '--memory-swap 128m', '--cpus 1', '--pids-limit 64',
                       '--read-only', '--tmpfs /tmp:rw,exec,size=64m', '--cap-drop ALL',
                       '--security-opt no-new-privileges', '--user 65534:65534', '--pull never']:
            self.assertIn(option, texte)
        montage = run[run.index('--mount') + 1]
        self.assertTrue(montage.startswith('type=bind,source='), montage)
        self.assertTrue(montage.endswith(',target=/code,readonly'), montage)
        self.assertIn('python:3.12-alpine', run)
        self.assertNotIn('--privileged', run)

    def test_lancement_par_test_avec_timeout(self):
        rapport, appels = self.lancer(scenario_normal(sorties=[(0, b'1\n', b''), (0, b'2\n', b'')]),
                                      cas=[{'entree': '1'}, {'entree': '2'}], temps=1500)
        execs = [a for a in appels if a[1] == 'exec']
        self.assertEqual(len(execs), 2)
        for e in execs:
            self.assertIn('-i', e)
            i = e.index('timeout')
            self.assertEqual(e[i:i + 4], ['timeout', '-s', 'KILL', '1.5'])
            self.assertEqual(e[i + 4:], ['python3', '-B', 'main.py'])
        self.assertTrue(rapport['compilation_ok'])
        self.assertEqual([r['sortie'] for r in rapport['resultats']], ['1\n', '2\n'])
        self.assertEqual(rapport['resultats'][0]['code_sortie'], 0)

    def test_compilation_une_seule_fois(self):
        rapport, appels = self.lancer(scenario_normal(), langage='c', fichiers=self.FICHIERS_C,
                                      cas=[{'entree': ''}, {'entree': ''}, {'entree': ''}])
        compilations = [a for a in appels if a[1] == 'exec' and '-i' not in a]
        self.assertEqual(len(compilations), 1)
        self.assertEqual(compilations[0][-6:], ['gcc', '-O2', '-o', '/tmp/prog', 'main.c', '-lm'])
        self.assertIn('gcc:13', self.commande_run(appels))
        lancements = [a for a in appels if a[1] == 'exec' and '-i' in a]
        self.assertEqual(len(lancements), 3)
        self.assertEqual(lancements[0][-1], '/tmp/prog')
        self.assertTrue(rapport['compilation_ok'])

    def test_compilation_en_echec(self):
        rapport, appels = self.lancer(scenario_normal(compilation=(1, b'', b'main.c:1: error')), langage='c',
                                      fichiers=self.FICHIERS_C)
        self.assertFalse(rapport['compilation_ok'])
        self.assertIn('main.c:1: error', rapport['compilation'])
        self.assertEqual(rapport['resultats'], [])
        self.assertFalse([a for a in appels if a[1] == 'exec' and '-i' in a])
        self.assertTrue([a for a in appels if a[1] == 'rm'])

    def test_conteneur_supprime_meme_en_cas_d_exception(self):
        def scenario(args):
            if args[1] == 'exec':
                return RuntimeError('panne'), b'', b''
            return scenario_normal()(args)
        appels = []
        with mock.patch.object(module_docker.subprocess, 'Popen', FauxProcessus(scenario, appels)):
            with self.assertRaises(RuntimeError):
                ExecuteurDocker().lancer('python', self.FICHIERS_PY, [{'entree': ''}], 2000, 256)
        nom = self.commande_run(appels)[self.commande_run(appels).index('--name') + 1]
        self.assertEqual(appels[-1], ['docker', 'rm', '-f', nom])

    def test_dossier_temporaire_supprime(self):
        dossiers = []
        vrai = module_docker.tempfile.mkdtemp

        def mkdtemp(**kwargs):
            dossiers.append(vrai(**kwargs))
            return dossiers[-1]
        with mock.patch.object(module_docker.tempfile, 'mkdtemp', mkdtemp):
            self.lancer(scenario_normal())
        self.assertFalse(os.path.exists(dossiers[0]))

    def test_docker_absent(self):
        def scenario(args):
            return FileNotFoundError('docker'), b'', b''
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario)

    def test_demarrage_en_echec(self):
        def scenario(args):
            if args[1] == 'run':
                return 125, b'', b'Cannot connect to the Docker daemon'
            return 0, b'', b''
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario)

    def test_demarrage_bloque(self):
        def scenario(args):
            if args[1] == 'run':
                return 'bloque', b'', b''
            return 0, b'', b''
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario)

    def test_nom_de_fichier_avec_chemin_refuse(self):
        with self.assertRaises(FichierInvalide):
            self.lancer(scenario_normal(), fichiers=[{'nom': '../main.py', 'contenu': ''}])

    def test_delai_depasse_code_124(self):
        rapport, _ = self.lancer(scenario_normal(exec_code=124))
        self.assertTrue(rapport['resultats'][0]['delai_depasse'])

    def test_oom(self):
        rapport, appels = self.lancer(scenario_normal(exec_code=137, inspect=b'{"Running":true,"OOMKilled":true}'))
        self.assertTrue(rapport['resultats'][0]['memoire_depassee'])
        self.assertFalse(rapport['resultats'][0]['delai_depasse'])
        self.assertTrue([a for a in appels if a[1] == 'inspect'])

    def test_code_137_rapide_sans_drapeau_oom(self):
        rapport, _ = self.lancer(scenario_normal(exec_code=137))
        self.assertTrue(rapport['resultats'][0]['memoire_depassee'])

    def test_code_137_apres_le_delai_est_un_depassement_de_temps(self):
        with mock.patch.object(module_docker.time, 'monotonic', side_effect=itertools.count(0.0, 5.0)):
            rapport, _ = self.lancer(scenario_normal(exec_code=137), temps=2000)
        self.assertTrue(rapport['resultats'][0]['delai_depasse'])
        self.assertFalse(rapport['resultats'][0]['memoire_depassee'])

    def test_conteneur_arrete_sans_oom(self):
        with self.assertRaises(ServiceIndisponible):
            self.lancer(scenario_normal(exec_code=137, inspect=b'{"Running":false,"OOMKilled":false}'))

    def test_erreur_execution(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[(1, b'', b'Traceback')]))
        r = rapport['resultats'][0]
        self.assertEqual((r['code_sortie'], r['erreurs'], r['delai_depasse'], r['memoire_depassee']),
                         (1, 'Traceback', False, False))

    def test_client_docker_bloque_pendant_un_test(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[('bloque', b'', b'')]))
        self.assertTrue(rapport['resultats'][0]['erreur_service'])

    def test_java_hors_memoire(self):
        rapport, appels = self.lancer(
            scenario_normal(sorties=[(3, b'', b'Terminating due to java.lang.OutOfMemoryError: Java heap space')]),
            langage='java', fichiers=[{'nom': 'Main.java', 'contenu': 'class Main{}'}])
        self.assertTrue(rapport['resultats'][0]['memoire_depassee'])
        self.assertIn('eclipse-temurin:21-jdk', self.commande_run(appels))

    def test_sorties_tronquees(self):
        rapport, _ = self.lancer(scenario_normal(sorties=[(0, b'x' * (TAILLE_MAX_SORTIE * 3), b'')]))
        self.assertEqual(len(rapport['resultats'][0]['sortie']), TAILLE_MAX_SORTIE)

    @override_settings(PEL_IMAGES_EXECUTION={'python': 'mon/python:1'})
    def test_image_surchargee(self):
        _, appels = self.lancer(scenario_normal())
        self.assertIn('mon/python:1', self.commande_run(appels))

    def test_langage_non_pris_en_charge(self):
        with self.assertRaises(ValueError):
            self.lancer(scenario_normal(), langage='autre')


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
