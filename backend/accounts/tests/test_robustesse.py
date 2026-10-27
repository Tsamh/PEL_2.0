from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from quiz.models import Quiz
from referentiel.models import AffectationEnseignant

U = '/api/accounts/users'


class DashboardEtudiantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_quiz_disponibles_limites_aux_filieres_de_l_etudiant(self):
        a = self.w.a
        Quiz.objects.create(titre='Brouillon A', filiere=a.filiere, niveau=self.w.niveau,
                            annee_academique=a.annee, est_publie=False, cree_par=a.ens)
        res = client_for(a.etu).get(f'{U}/dashboard_stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['quiz_disponibles'], 1)
        self.assertGreaterEqual(Quiz.objects.filter(est_publie=True).count(), 2)


class DashboardEnseignantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_soumissions_a_corriger_comptent_la_correction_automatique(self):
        from programming.models import SoumissionDevoir
        a = self.w.a
        for i, statut in enumerate(('soumis', 'en_correction', 'corrigee_auto', 'corrige')):
            etu = make_user(f'etu_dash{i}', 'etudiant', a.etab)
            SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=etu, statut=statut)
        res = client_for(a.ens).get(f'{U}/dashboard_stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data['soumissions_recues'], res.data['soumissions_a_corriger']), (4, 3))


class EntreesInvalidesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_update_classes_refuse_une_liste_invalide(self):
        a = self.w.a
        url = f'{U}/{a.ens.id}/update_classes/'
        for classes in ('abc', ['x'], {'a': 1}, [[1]], 5, [True]):
            with self.subTest(classes=classes):
                res = client_for(a.admin).post(url, {'classes': classes}, format='json')
                self.assertEqual(res.status_code, 400)
                self.assertIn('classes', res.data['error'])
        self.assertTrue(AffectationEnseignant.objects.filter(enseignant=a.ens, classe=a.classe).exists())

    def test_invite_enseignant_refuse_une_liste_invalide(self):
        a = self.w.a
        for classes in ('abc', ['x'], {'a': 1}):
            with self.subTest(classes=classes):
                res = client_for(a.admin).post(f'{U}/invite_enseignant/', {
                    'email': 'prof.neuf@test.pel', 'first_name': 'P', 'last_name': 'N', 'classes': classes,
                }, format='json')
                self.assertEqual(res.status_code, 400)

    def test_invite_responsable_admin_sans_etablissement(self):
        orphelin = make_user('adminOrphelin', 'admin', None)
        res = client_for(orphelin).post(f'{U}/invite_responsable/', {
            'email': 'resp.orphelin@test.pel', 'first_name': 'R', 'last_name': 'O',
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(email='resp.orphelin@test.pel').exists())
