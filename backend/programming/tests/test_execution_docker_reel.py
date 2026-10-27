"""Intégration avec un vrai Docker : ignorée sauf si PEL_TEST_DOCKER=1 (images tirées au préalable)."""
import os
import unittest

from django.test import SimpleTestCase

from programming.execution.docker import ExecuteurDocker
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
