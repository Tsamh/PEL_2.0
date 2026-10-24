from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from referentiel.models import Classe, Groupe, Inscription

Q = '/api/quiz/quizzes'
T = '/api/quiz/tentatives'


class VisibiliteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.quiz.classes.clear()
        self.voisin = make_user('voisin', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=self.voisin, classe=self.a.classe)

    def ids(self, user):
        res = client_for(user).get(f'{Q}/')
        self.assertEqual(res.status_code, 200)
        return {q['id'] for q in res.data['results']}

    def assert_invisible(self, user):
        client = client_for(user)
        self.assertNotIn(self.quiz.id, self.ids(user))
        self.assertEqual(client.get(f'{Q}/{self.quiz.id}/').status_code, 404)
        self.assertEqual(client.post(f'{Q}/{self.quiz.id}/demarrer/').status_code, 404)

    def test_sans_affectation_invisible(self):
        self.assert_invisible(self.a.etu)
        self.assert_invisible(self.voisin)

    def test_affecte_par_classe(self):
        self.quiz.classes.add(self.a.classe)
        self.assertIn(self.quiz.id, self.ids(self.a.etu))
        self.assertIn(self.quiz.id, self.ids(self.voisin))

    def test_affecte_par_groupe(self):
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.a.etu)
        self.quiz.groupes.add(groupe)
        self.assertIn(self.quiz.id, self.ids(self.a.etu))
        self.assert_invisible(self.voisin)

    def test_affecte_nominativement(self):
        self.quiz.etudiants.add(self.voisin)
        self.assertIn(self.quiz.id, self.ids(self.voisin))
        self.assert_invisible(self.a.etu)

    def test_meme_filiere_autre_classe_non_affecte(self):
        self.quiz.classes.add(self.a.classe)
        autre_classe = Classe.objects.create(
            code='L1X', libelle='L1 Info X', filiere=self.a.filiere, niveau=self.w.niveau,
            annee_academique=self.a.annee,
        )
        autre = make_user('autre', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=autre, classe=autre_classe)
        self.assert_invisible(autre)

    def test_inscrit_apres_affectation(self):
        self.quiz.classes.add(self.a.classe)
        nouveau = make_user('nouveau', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=nouveau, classe=self.a.classe)
        self.assertIn(self.quiz.id, self.ids(nouveau))

    def test_non_publie_invisible(self):
        self.quiz.classes.add(self.a.classe)
        self.quiz.est_publie = False
        self.quiz.save()
        self.assert_invisible(self.a.etu)

    def test_pas_de_doublon_avec_plusieurs_cibles(self):
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.a.etu)
        self.quiz.classes.add(self.a.classe)
        self.quiz.groupes.add(groupe)
        self.quiz.etudiants.add(self.a.etu)
        res = client_for(self.a.etu).get(f'{Q}/')
        self.assertEqual([q['id'] for q in res.data['results']].count(self.quiz.id), 1)

    def test_retrait_conserve_la_tentative(self):
        self.quiz.etudiants.add(self.voisin)
        client = client_for(self.voisin)
        res = client.post(f'{Q}/{self.quiz.id}/demarrer/')
        self.assertEqual(res.status_code, 201)
        tentative_id = res.data['id']
        self.quiz.etudiants.remove(self.voisin)
        self.assertEqual(client.post(f'{Q}/{self.quiz.id}/demarrer/').status_code, 404)
        self.assertEqual(client.get(f'{T}/{tentative_id}/').status_code, 200)
        self.assertEqual(client.post(f'{T}/{tentative_id}/soumettre/').status_code, 200)
        liste = client.get(f'{T}/').data
        ids = {t['id'] for t in (liste['results'] if isinstance(liste, dict) else liste)}
        self.assertIn(tentative_id, ids)

    def test_tableau_de_bord(self):
        url = '/api/accounts/users/dashboard_stats/'
        self.assertEqual(client_for(self.a.etu).get(url).data['quiz_disponibles'], 0)
        self.quiz.classes.add(self.a.classe)
        self.assertEqual(client_for(self.a.etu).get(url).data['quiz_disponibles'], 1)
