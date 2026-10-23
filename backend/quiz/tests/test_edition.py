from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for
from quiz.models import Choix, Question, Quiz, TentativeQuiz

Q = '/api/quiz'


def qcm(texte='Capitale ?', points=1, mode='tout_ou_rien', choix=None):
    return {
        'texte': texte, 'type_question': 'qcm', 'points': points, 'mode_notation': mode,
        'choix': choix if choix is not None else [
            {'texte': 'Paris', 'est_correct': True}, {'texte': 'Lyon', 'est_correct': False},
        ],
    }


class CoherenceQuestionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def creer(self, questions, **extra):
        a = self.w.a
        corps = {'titre': 'Nouveau', 'filiere': a.filiere.id, 'questions': questions, **extra}
        return client_for(a.ens).post(f'{Q}/quizzes/', corps, format='json')

    def test_creation_imbriquee_des_trois_types(self):
        res = self.creer([
            qcm(),
            {'texte': 'La Terre est ronde', 'type_question': 'vf', 'points': '0.5',
             'choix': [{'texte': 'Vrai', 'est_correct': True}, {'texte': 'Faux', 'est_correct': False}]},
            {'texte': 'Capitale de la France ?', 'type_question': 'courte', 'points': 2,
             'choix': [{'texte': 'Paris', 'est_correct': True}]},
        ])
        self.assertEqual(res.status_code, 201, res.data)
        quiz = Quiz.objects.get(pk=res.data['id'])
        self.assertEqual(quiz.questions.count(), 3)
        self.assertEqual(quiz.questions.get(type_question='vf').points, Decimal('0.50'))

    def test_qcm_multi_par_choix(self):
        res = self.creer([qcm(points=1, mode='par_choix', choix=[
            {'texte': 'a', 'est_correct': True, 'points': '0.5'},
            {'texte': 'b', 'est_correct': True, 'points': '0.5'},
            {'texte': 'c', 'est_correct': False, 'points': '-0.25'},
        ])])
        self.assertEqual(res.status_code, 201, res.data)
        question = Question.objects.get(quiz_id=res.data['id'])
        self.assertTrue(question.est_multiple)
        self.assertEqual(question.choix.get(texte='c').points, Decimal('-0.25'))

    def test_incoherences_refusees(self):
        cas = {
            'vf deux bonnes': {'texte': 'x', 'type_question': 'vf', 'choix': [
                {'texte': 'Vrai', 'est_correct': True}, {'texte': 'Faux', 'est_correct': True}]},
            'vf trois choix': {'texte': 'x', 'type_question': 'vf', 'choix': [
                {'texte': 'Vrai', 'est_correct': True}, {'texte': 'Faux'}, {'texte': 'Autre'}]},
            'qcm sans bonne': qcm(choix=[{'texte': 'a'}, {'texte': 'b'}]),
            'qcm un seul choix': qcm(choix=[{'texte': 'a', 'est_correct': True}]),
            'par choix somme fausse': qcm(points=1, mode='par_choix', choix=[
                {'texte': 'a', 'est_correct': True, 'points': '0.5'}, {'texte': 'b', 'points': '0'}]),
            'courte sans réponse': {'texte': 'x', 'type_question': 'courte', 'choix': [{'texte': ' ', 'est_correct': True}]},
            'points nuls': qcm(points=0),
        }
        for nom, question in cas.items():
            with self.subTest(cas=nom):
                self.assertEqual(self.creer([question]).status_code, 400)
        self.assertFalse(Quiz.objects.filter(titre='Nouveau').exists())

    def test_reglages_invalides(self):
        maintenant = timezone.now()
        self.assertEqual(self.creer([qcm()], tentatives_autorisees=0).status_code, 400)
        self.assertEqual(self.creer([qcm()], date_debut=maintenant.isoformat(),
                                    date_fin=(maintenant - timedelta(hours=1)).isoformat()).status_code, 400)


class VerrouillageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        a = self.w.a
        TentativeQuiz.objects.create(quiz=a.quiz, etudiant=a.etu, fin_prevue=timezone.now())
        self.client_ens = client_for(a.ens)

    def test_a_des_tentatives_expose(self):
        a, b = self.w.a, self.w.b
        self.assertTrue(self.client_ens.get(f'{Q}/quizzes/{a.quiz.id}/').data['a_des_tentatives'])
        self.assertFalse(client_for(b.ens).get(f'{Q}/quizzes/{b.quiz.id}/').data['a_des_tentatives'])

    def test_questions_verrouillees_via_le_quiz(self):
        a = self.w.a
        res = self.client_ens.patch(f'{Q}/quizzes/{a.quiz.id}/', {'questions': [qcm()]}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(list(a.quiz.questions.values_list('id', flat=True)), [a.question.id])

    def test_reglages_toujours_modifiables(self):
        a = self.w.a
        res = self.client_ens.patch(f'{Q}/quizzes/{a.quiz.id}/', {'titre': 'Renommé', 'tentatives_autorisees': 3}, format='json')
        self.assertEqual(res.status_code, 200, res.data)

    def test_endpoints_questions_et_choix_verrouilles(self):
        a = self.w.a
        choix = a.question.choix.first()
        appels = [
            ('post', f'{Q}/questions/', {'quiz': a.quiz.id, 'texte': 'Nouvelle ?'}),
            ('patch', f'{Q}/questions/{a.question.id}/', {'texte': 'Modifiée ?'}),
            ('delete', f'{Q}/questions/{a.question.id}/', None),
            ('post', f'{Q}/choix/', {'question': a.question.id, 'texte': 'Nouveau'}),
            ('patch', f'{Q}/choix/{choix.id}/', {'texte': 'Modifié'}),
            ('delete', f'{Q}/choix/{choix.id}/', None),
        ]
        for methode, url, corps in appels:
            with self.subTest(methode=methode, url=url):
                res = getattr(self.client_ens, methode)(url, corps, format='json')
                self.assertEqual(res.status_code, 409)
        self.assertEqual(Question.objects.filter(quiz=a.quiz).count(), 1)
        self.assertEqual(Choix.objects.filter(question=a.question).count(), 2)
        self.assertEqual(Question.objects.get(pk=a.question.pk).texte, '2 + 2 ?')
