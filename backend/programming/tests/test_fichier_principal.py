"""Fichier principal Java (Main.java) et fichier principal obligatoire (sous-projet 4c, tâche 1)."""
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from accounts.testing import build_world, client_for
from programming.execution import langages
from programming.models import Devoir

P = '/api/programming'
AVANT = [('programming', '0008_execution')]
APRES = [('programming', '0009_main_java')]


class LangagesTests(SimpleTestCase):
    def test_fichier_principal(self):
        self.assertEqual(langages.fichier_principal('java'), 'Main.java')
        self.assertEqual(langages.fichier_principal('python'), 'main.py')
        self.assertEqual(langages.fichier_principal('cpp'), 'main.cpp')
        self.assertIsNone(langages.fichier_principal('autre'))

    def test_message_principal(self):
        self.assertEqual(langages.message_principal('java', [{'nom': 'main.java', 'contenu': ''}]),
                         "Le fichier principal Main.java est obligatoire.")
        self.assertEqual(langages.message_principal('python', []), "Le fichier principal main.py est obligatoire.")
        self.assertIsNone(langages.message_principal('java', [{'nom': 'Main.java', 'contenu': ''}]))
        self.assertIsNone(langages.message_principal('autre', []))


@override_settings(PEL_EXECUTEUR='factice')
class PrincipalObligatoireTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        cache.clear()
        self.a = self.w.a
        self.etu = client_for(self.a.etu)
        self.ex = self.a.exercice

    def soumettre(self, fichiers):
        return self.etu.post(f'{P}/soumissions/', {
            'devoir': self.a.devoir.id, 'reponses': [{'exercice': self.ex.id, 'fichiers': fichiers}]}, format='json')

    def executer(self, fichiers):
        return self.etu.post(f'{P}/devoirs/{self.a.devoir.id}/executer/',
                             {'exercice': self.ex.id, 'fichiers': fichiers, 'mode': 'run'}, format='json')

    def test_soumission_sans_principal_400(self):
        for fichiers in ([], [{'nom': 'autre.py', 'contenu': ''}], [{'nom': 'MAIN.py', 'contenu': ''}]):
            with self.subTest(fichiers=fichiers):
                res = self.soumettre(fichiers)
                self.assertEqual(res.status_code, 400, res.data)
                self.assertIn("Le fichier principal main.py est obligatoire.", str(res.data['reponses']))
        self.assertEqual(self.a.devoir.soumissions.count(), 0)
        self.assertEqual(self.soumettre([{'nom': 'main.py', 'contenu': ''}]).status_code, 201)

    def test_executer_sans_principal_400(self):
        res = self.executer([{'nom': 'autre.py', 'contenu': ''}])
        self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(str(res.data['fichiers'][0]), "Le fichier principal main.py est obligatoire.")
        self.assertEqual(self.executer([{'nom': 'main.py', 'contenu': ''}]).status_code, 202)

    def test_java_exige_main_java(self):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='java')
        res = self.executer([{'nom': 'main.java', 'contenu': ''}])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['fichiers'][0]), "Le fichier principal Main.java est obligatoire.")
        self.assertEqual(self.executer([{'nom': 'Main.java', 'contenu': ''}]).status_code, 202)

    def test_autre_sans_regle(self):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='autre')
        self.assertEqual(self.soumettre([]).status_code, 201)

    def test_champ_fichier_principal_expose(self):
        url = f'{P}/devoirs/{self.a.devoir.id}/'
        self.assertEqual(client_for(self.a.ens).get(url).data['fichier_principal'], 'main.py')
        self.assertEqual(self.etu.get(url).data['fichier_principal'], 'main.py')
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='java')
        self.assertEqual(self.etu.get(url).data['fichier_principal'], 'Main.java')
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='autre')
        self.assertIsNone(self.etu.get(url).data['fichier_principal'])
        self.assertIsNone(client_for(self.a.ens).get(url).data['fichier_principal'])


class MigrationMainJavaTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(AVANT)
        autres = [n for n in executor.loader.graph.leaf_nodes() if n[0] != 'programming']
        apps = executor.loader.project_state(AVANT + autres).apps
        User = apps.get_model('accounts', 'User')
        Devoir = apps.get_model('programming', 'Devoir')
        Exercice = apps.get_model('programming', 'Exercice')
        Soumission = apps.get_model('programming', 'SoumissionDevoir')
        Reponse = apps.get_model('programming', 'ReponseExercice')
        etu = User.objects.create(username='etuMJ', role='etudiant')

        def fic(*noms):
            return [{'nom': n, 'contenu': f'// {n}'} for n in noms]

        def devoir(titre, langage, initiaux, solution, reponse):
            d = Devoir.objects.create(titre=titre, langage=langage)
            e = Exercice.objects.create(devoir=d, ordre=1, titre=titre, fichiers_initiaux=initiaux, solution=solution)
            s = Soumission.objects.create(devoir=d, etudiant=etu)
            Reponse.objects.create(soumission=s, exercice=e, fichiers=reponse)
            return e.pk, s.pk

        self.java = devoir('Java', 'java', fic('main.java', 'Aide.java'), fic('main.java'), fic('main.java'))
        self.deja = devoir('Deja', 'java', fic('main.java', 'Main.java'), fic('Main.java', 'main.java'),
                           fic('main.java', 'Main.java'))
        self.python = devoir('Python', 'python', fic('main.py'), fic('main.py'), fic('main.py'))
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(APRES)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def noms(self, ids):
        from programming.models import Exercice, ReponseExercice

        exercice = Exercice.objects.get(pk=ids[0])
        reponse = ReponseExercice.objects.get(soumission_id=ids[1])
        return ([f['nom'] for f in exercice.fichiers_initiaux], [f['nom'] for f in exercice.solution],
                [f['nom'] for f in reponse.fichiers])

    def test_main_java_renomme(self):
        self.assertEqual(self.noms(self.java), (['Main.java', 'Aide.java'], ['Main.java'], ['Main.java']))
        from programming.models import Exercice

        self.assertEqual(Exercice.objects.get(pk=self.java[0]).fichiers_initiaux[0]['contenu'], '// main.java')

    def test_laisse_tel_quel_si_main_java_existe(self):
        self.assertEqual(self.noms(self.deja), (['main.java', 'Main.java'], ['Main.java', 'main.java'],
                                                ['main.java', 'Main.java']))

    def test_autres_langages_intacts(self):
        self.assertEqual(self.noms(self.python), (['main.py'], ['main.py'], ['main.py']))
