"""Limites d'exécution, politique de résultats, file d'exécution et statuts de soumission (sous-projet 4b)."""
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from accounts.testing import build_world, client_for
from programming.models import Devoir, Execution, Exercice, ResultatTest, SoumissionDevoir
from programming.tests.test_devoirs_api import MESSAGE_VERROU, P, exercice

URL_ETUDIANT = '/api/programming/devoirs'


class ConstantesTests(TestCase):
    def test_constantes(self):
        self.assertEqual((Execution.ESSAI_RUN, Execution.ESSAI_TEST, Execution.CORRECTION),
                         ('essai_run', 'essai_test', 'correction'))
        self.assertEqual((Execution.EN_ATTENTE, Execution.EN_COURS, Execution.TERMINEE, Execution.ERREUR),
                         ('en_attente', 'en_cours', 'terminee', 'erreur'))
        self.assertEqual((ResultatTest.OK, ResultatTest.CE, ResultatTest.RE, ResultatTest.WA, ResultatTest.TLE,
                          ResultatTest.MLE, ResultatTest.SE), ('OK', 'CE', 'RE', 'WA', 'TLE', 'MLE', 'SE'))
        self.assertEqual((SoumissionDevoir.SOUMIS, SoumissionDevoir.EN_CORRECTION, SoumissionDevoir.CORRIGEE_AUTO,
                          SoumissionDevoir.CORRIGE), ('soumis', 'en_correction', 'corrigee_auto', 'corrige'))
        self.assertEqual((Devoir.APRES_VALIDATION, Devoir.IMMEDIATE), ('apres_validation', 'immediate'))

    def test_reglages(self):
        self.assertEqual(settings.PEL_EXECUTEUR, 'docker')
        self.assertEqual(settings.PEL_WORKERS_EXECUTION, 2)
        self.assertEqual(settings.PEL_IMAGES_EXECUTION['python'], 'python:3.12-alpine')
        self.assertEqual(settings.PEL_IMAGES_EXECUTION['javascript'], 'node:20-alpine')
        self.assertEqual(settings.PEL_IMAGES_EXECUTION['c'], 'gcc:13')
        self.assertEqual(settings.PEL_IMAGES_EXECUTION['cpp'], 'gcc:13')
        self.assertEqual(settings.PEL_IMAGES_EXECUTION['java'], 'eclipse-temurin:21-jdk')


class LimitesApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a

    def creer(self, exercices=None, **extra):
        data = {'titre': 'TP', 'filiere': self.a.filiere.id, 'langage': 'python', 'classes': [self.a.classe.id],
                'exercices': exercices if exercices is not None else [exercice()]}
        data.update(extra)
        return client_for(self.a.ens).post(f'{P}/', data, format='json')

    def patch(self, devoir_id, data):
        return client_for(self.a.ens).patch(f'{P}/{devoir_id}/', data, format='json')

    def soumettre(self, devoir):
        SoumissionDevoir.objects.create(devoir=devoir, etudiant=self.a.etu)

    def test_valeurs_par_defaut(self):
        res = self.creer()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['politique_resultats'], 'apres_validation')
        self.assertEqual(res.data['exercices'][0]['limite_temps_ms'], 2000)
        self.assertEqual(res.data['exercices'][0]['limite_memoire_mo'], 256)

    def test_limites_enregistrees(self):
        res = self.creer([exercice(limite_temps_ms=100, limite_memoire_mo=512)], politique_resultats='immediate')
        self.assertEqual(res.status_code, 201, res.data)
        e = Exercice.objects.get(devoir_id=res.data['id'])
        self.assertEqual((e.limite_temps_ms, e.limite_memoire_mo), (100, 512))
        self.assertEqual(Devoir.objects.get(pk=res.data['id']).politique_resultats, 'immediate')
        res = self.creer([exercice(limite_temps_ms=10000, limite_memoire_mo=16)])
        self.assertEqual(res.status_code, 201, res.data)

    def test_bornes_refusees(self):
        for champ, valeur in (('limite_temps_ms', 99), ('limite_temps_ms', 10001),
                              ('limite_memoire_mo', 15), ('limite_memoire_mo', 513)):
            with self.subTest(champ=champ, valeur=valeur):
                res = self.creer([exercice(**{champ: valeur})])
                self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(self.creer(politique_resultats='jamais').status_code, 400)

    def test_limite_modifiee_apres_soumission_verrouillee(self):
        devoir = Devoir.objects.get(pk=self.creer().data['id'])
        self.soumettre(devoir)
        for champ, valeur in (('limite_temps_ms', 3000), ('limite_memoire_mo', 128)):
            with self.subTest(champ=champ):
                res = self.patch(devoir.id, {'exercices': [exercice(**{champ: valeur})]})
                self.assertEqual(res.status_code, 409, res.data)
                self.assertEqual(str(res.data['detail']), MESSAGE_VERROU)
        # Limites identiques : rien n'est réécrit.
        res = self.patch(devoir.id, {'exercices': [exercice()]})
        self.assertEqual(res.status_code, 200, res.data)

    def test_politique_modifiee_apres_soumission(self):
        devoir = Devoir.objects.get(pk=self.creer().data['id'])
        self.soumettre(devoir)
        res = self.patch(devoir.id, {'politique_resultats': 'immediate'})
        self.assertEqual(res.status_code, 200, res.data)
        devoir.refresh_from_db()
        self.assertEqual(devoir.politique_resultats, 'immediate')

    def test_etudiant_voit_les_limites_pas_la_solution(self):
        res = self.creer([exercice(limite_temps_ms=1500, limite_memoire_mo=64)], est_publie=True)
        self.assertEqual(res.status_code, 201, res.data)
        lu = client_for(self.a.etu).get(f'{URL_ETUDIANT}/{res.data["id"]}/')
        self.assertEqual(lu.status_code, 200, lu.data)
        ex = lu.data['exercices'][0]
        self.assertEqual((ex['limite_temps_ms'], ex['limite_memoire_mo']), (1500, 64))
        self.assertNotIn('solution', ex)
        self.assertNotIn('SOLUTION_SECRETE', str(lu.data))
        self.assertNotIn('SORTIE_CACHEE', str(lu.data))


class MigrationExecutionTests(TransactionTestCase):
    AVANT = [('programming', '0007_retrait_anciens_champs')]

    def test_soumissions_existantes_conservees(self):
        executor = MigrationExecutor(connection)
        apres = [executor.loader.graph.leaf_nodes('programming')[0]]
        executor.migrate(self.AVANT)
        autres = [n for n in executor.loader.graph.leaf_nodes() if n[0] != 'programming']
        apps = executor.loader.project_state(self.AVANT + autres).apps
        User = apps.get_model('accounts', 'User')
        Devoir_ = apps.get_model('programming', 'Devoir')
        Soumission = apps.get_model('programming', 'SoumissionDevoir')
        u1 = User.objects.create(username='mig1', role='etudiant')
        u2 = User.objects.create(username='mig2', role='etudiant')
        devoir = Devoir_.objects.create(titre='Ancien')
        Soumission.objects.create(devoir=devoir, etudiant=u1, statut='soumis')
        Soumission.objects.create(devoir=devoir, etudiant=u2, statut='corrige', score=3)

        executor = MigrationExecutor(connection)
        executor.migrate(apres)
        apps = executor.loader.project_state(apres).apps
        Soumission = apps.get_model('programming', 'SoumissionDevoir')
        Devoir_ = apps.get_model('programming', 'Devoir')
        self.assertEqual(Soumission.objects.get(etudiant__username='mig1').statut, 'soumis')
        corrigee = Soumission.objects.get(etudiant__username='mig2')
        self.assertEqual((corrigee.statut, corrigee.score, corrigee.note_proposee), ('corrige', 3, None))
        self.assertEqual(Devoir_.objects.get(titre='Ancien').politique_resultats, 'apres_validation')
