import json

from django.test import TestCase

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from quiz.models import Quiz, Question

Q = '/api/quiz'


def ids(res):
    return {o['id'] for o in res.data['results']}


class LectureQuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_etudiant_ne_recoit_jamais_est_correct(self):
        a = self.w.a
        client = client_for(a.etu)
        for url in (f'{Q}/quizzes/', f'{Q}/quizzes/{a.quiz.id}/'):
            with self.subTest(url=url):
                res = client.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertNotIn('est_correct', json.dumps(res.data))

    def test_etudiant_ne_voit_que_les_quiz_publies_de_ses_filieres(self):
        a, b = self.w.a, self.w.b
        Quiz.objects.create(titre='Brouillon', filiere=a.filiere, est_publie=False, cree_par=a.ens)
        self.assertEqual(ids(client_for(a.etu).get(f'{Q}/quizzes/')), {a.quiz.id})
        self.assertEqual(client_for(a.etu).get(f'{Q}/quizzes/{b.quiz.id}/').status_code, 404)

    def test_questions_et_choix_fermes_aux_etudiants(self):
        for url in (f'{Q}/questions/', f'{Q}/choix/'):
            with self.subTest(url=url):
                self.assertEqual(client_for(self.w.a.etu).get(url).status_code, 403)

    def test_enseignant_voit_ses_quiz_et_les_bonnes_reponses(self):
        a = self.w.a
        res = client_for(a.ens).get(f'{Q}/quizzes/')
        self.assertEqual(ids(res), {a.quiz.id})
        self.assertIn('est_correct', json.dumps(res.data))

    def test_admin_voit_son_etablissement(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(ids(client_for(a.admin).get(f'{Q}/quizzes/')), {a.quiz.id})
        self.assertEqual(client_for(a.admin).put(f'{Q}/quizzes/{b.quiz.id}/', {}, format='json').status_code, 404)

    def test_questions_filtrees(self):
        a = self.w.a
        self.assertEqual(ids(client_for(a.ens).get(f'{Q}/questions/')), {a.question.id})
        self.assertEqual(ids(client_for(a.resp).get(f'{Q}/questions/')), {a.question.id})


class EcritureQuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_etudiant_ne_peut_pas_creer(self):
        res = client_for(self.w.a.etu).post(f'{Q}/quizzes/', {'titre': 'X'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_cree_par_impose(self):
        a = self.w.a
        res = client_for(a.ens).post(f'{Q}/quizzes/', {'titre': 'Mon quiz', 'filiere': a.filiere.id, 'cree_par': a.admin.id}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Quiz.objects.get(titre='Mon quiz').cree_par, a.ens)

    def test_filiere_hors_perimetre_refusee(self):
        a, b = self.w.a, self.w.b
        for user in (a.ens, a.admin):
            with self.subTest(role=user.role):
                res = client_for(user).post(f'{Q}/quizzes/', {'titre': f'Piège {user.role}', 'filiere': b.filiere.id}, format='json')
                self.assertEqual(res.status_code, 400)
        self.assertFalse(Quiz.objects.filter(titre__startswith='Piège').exists())

    def test_admin_garde_l_ecriture(self):
        a = self.w.a
        res = client_for(a.admin).post(f'{Q}/quizzes/', {'titre': 'Quiz admin', 'filiere': a.filiere.id}, format='json')
        self.assertEqual(res.status_code, 201)

    def test_enseignant_ne_peut_pas_ajouter_une_question_au_quiz_d_un_autre(self):
        a, b = self.w.a, self.w.b
        res = client_for(b.ens).post(f'{Q}/questions/', {'quiz': a.quiz.id, 'texte': 'Intrus ?'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Question.objects.filter(texte='Intrus ?').exists())

    def test_publication_et_suppression_journalisees(self):
        a = self.w.a
        client = client_for(a.ens)
        res = client.post(f'{Q}/quizzes/', {'titre': 'Brouillon', 'filiere': a.filiere.id, 'est_publie': False}, format='json')
        quiz_id = res.data['id']
        self.assertFalse(AuditLog.objects.filter(action='publication_evaluation').exists())
        client.patch(f'{Q}/quizzes/{quiz_id}/', {'est_publie': True}, format='json')
        entree = AuditLog.objects.get(action='publication_evaluation')
        self.assertEqual(entree.etablissement, a.etab)
        client.patch(f'{Q}/quizzes/{quiz_id}/', {'titre': 'Renommé'}, format='json')
        self.assertEqual(AuditLog.objects.filter(action='publication_evaluation').count(), 1)
        self.assertEqual(client.delete(f'{Q}/quizzes/{quiz_id}/').status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action='suppression_evaluation', details__titre='Renommé').exists())
