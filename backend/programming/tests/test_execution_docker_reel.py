"""Intégration avec un vrai Docker : ignorée sauf si PEL_TEST_DOCKER=1 (images tirées au préalable).

PEL_TEST_DOCKER=1 ./env/Scripts/python.exe manage.py test programming.tests.test_execution_docker_reel
"""
import os
import unittest

from django.test import SimpleTestCase

from programming.execution.docker import ExecuteurDocker, nettoyer_orphelins
from programming.execution.executeur import statut_du_resultat

ACTIF = os.environ.get('PEL_TEST_DOCKER') == '1'


@unittest.skipUnless(ACTIF, "Définir PEL_TEST_DOCKER=1 pour lancer les tests avec un vrai Docker.")
class DockerReelTests(SimpleTestCase):
    def statuts(self, langage, nom, contenu, cas, attendues, temps=2000, memoire=128):
        rapport = ExecuteurDocker().lancer(langage, [{'nom': nom, 'contenu': contenu}],
                                           [{'entree': e} for e in cas], temps, memoire)
        return rapport, [statut_du_resultat(rapport['compilation_ok'], r, a)
                         for r, a in zip(rapport['resultats'] or [None] * len(cas), attendues)]

    def test_python_ok_et_wa(self):
        _, statuts = self.statuts('python', 'main.py', 'a, b = map(int, input().split())\nprint(a + b)\n',
                                  ['1 2', '40 2'], ['3', '41'])
        self.assertEqual(statuts, ['OK', 'WA'])

    def test_python_re(self):
        _, statuts = self.statuts('python', 'main.py', 'raise SystemExit(3)\n', [''], [''])
        self.assertEqual(statuts, ['RE'])

    def test_python_tle(self):
        _, statuts = self.statuts('python', 'main.py', 'while True:\n    pass\n', [''], [''], temps=500)
        self.assertEqual(statuts, ['TLE'])

    def test_python_mle(self):
        _, statuts = self.statuts('python', 'main.py', 'x = bytearray(512 * 1024 * 1024)\n', [''], [''], memoire=64)
        self.assertIn(statuts[0], ('MLE', 'RE'))  # MemoryError Python (RE) ou tué par le noyau (MLE)

    def test_pas_de_reseau_ni_ecriture(self):
        code = ("import socket, sys\n"
                "try:\n    socket.create_connection(('1.1.1.1', 80), timeout=1); print('reseau')\n"
                "except OSError: print('sans reseau')\n"
                "try:\n    open('/code/x', 'w'); print('ecriture')\n"
                "except OSError: print('lecture seule')\n")
        rapport, statuts = self.statuts('python', 'main.py', code, [''], ['sans reseau\nlecture seule'])
        self.assertEqual(statuts, ['OK'], rapport)

    def test_c_compile_et_lance(self):
        _, statuts = self.statuts('c', 'main.c', '#include <stdio.h>\nint main(){int a,b;scanf("%d %d",&a,&b);'
                                  'printf("%d\n",a+b);return 0;}\n', ['1 2', '2 2'], ['3', '4'])
        self.assertEqual(statuts, ['OK', 'OK'])

    def test_c_erreur_de_compilation(self):
        rapport, statuts = self.statuts('c', 'main.c', 'int main( {', ['', ''], ['', ''])
        self.assertEqual(statuts, ['CE', 'CE'])
        self.assertIn('error', rapport['compilation'])

    def test_java(self):
        _, statuts = self.statuts('java', 'Main.java', 'public class Main { public static void main(String[] a) '
                                  '{ System.out.println("ok"); } }', [''], ['ok'], temps=5000, memoire=256)
        self.assertEqual(statuts, ['OK'])

    def test_java_compile_avec_une_petite_limite(self):
        # La compilation a sa propre mémoire (512 Mo) : javac ne dépend pas de la limite de l'exercice.
        rapport, _ = self.statuts('java', 'Main.java', 'public class Main { public static void main(String[] a) '
                                  '{ System.out.println("ok"); } }', [''], ['ok'], temps=5000, memoire=64)
        self.assertTrue(rapport['compilation_ok'], rapport)

    def test_utilisateur_et_ecritures(self):
        code = ("import os\n"
                "print(os.getuid(), os.getgid())\n"
                "for chemin in ('/x', '/code/x', '/dev/shm/x', '/build/x'):\n"
                "    try:\n        open(chemin, 'w'); print('ecrit', chemin)\n"
                "    except OSError: pass\n"
                "open('/tmp/x', 'w').write('ok'); print('tmp')\n")
        rapport, statuts = self.statuts('python', 'main.py', code, [''], ['65534 65534\ntmp'])
        self.assertEqual(statuts, ['OK'], rapport)

    def test_sigkill_sur_soi_est_une_erreur_d_execution(self):
        _, statuts = self.statuts('python', 'main.py', 'import os\nos.kill(os.getpid(), 9)\n', [''], [''])
        self.assertEqual(statuts, ['RE'])

    def test_fork_bomb_bornee(self):
        code = "import os\nwhile True:\n    try:\n        os.fork()\n    except OSError:\n        pass\n"
        _, statuts = self.statuts('python', 'main.py', code, ['', ''], ['', ''], temps=1000)
        self.assertEqual(len(statuts), 2)
        self.assertNotIn('SE', statuts)

    def test_sortie_infinie_bornee(self):
        rapport, statuts = self.statuts('python', 'main.py', 'while True:\n    print("x" * 1000)\n', [''], [''],
                                        temps=1000)
        self.assertEqual(statuts, ['TLE'])
        self.assertLessEqual(len(rapport['resultats'][0]['sortie']), 64 * 1024)

    def test_processus_d_arriere_plan_qui_garde_la_sortie(self):
        # Le fils garde stdout ouvert après la fin du père : TLE, puis il est tué avant le test suivant.
        code = ("import os, sys, time\n"
                "if sys.stdin.read().strip() == 'fond':\n"
                "    if os.fork() == 0:\n        os.setsid(); time.sleep(600)\n"
                "print('fin')\n")
        rapport, statuts = self.statuts('python', 'main.py', code, ['fond', 'normal'], ['fin', 'fin'], temps=1000)
        self.assertEqual(statuts, ['TLE', 'OK'], rapport)

    def test_sortie_avec_nul(self):
        rapport, _ = self.statuts('c', 'main.c', '#include <stdio.h>\nint main(){putchar(97);putchar(0);'
                                  'putchar(98);return 0;}\n', [''], [''])
        self.assertEqual(rapport['resultats'][0]['sortie'], 'a\ufffdb')

    def test_nettoyage_des_orphelins(self):
        self.assertEqual(set(nettoyer_orphelins()), {'conteneurs', 'volumes', 'dossiers'})
