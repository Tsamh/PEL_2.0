import json
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for
from quiz.correction import corriger_tentative
from quiz.models import Choix, Question, ReponseQuiz, TentativeQuiz

Q = '/api/quiz'


class NotationPenaliteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.q = self.a.question
        self.q.penalite = Decimal('0.5')
        self.q.save()
        self.bon = self.q.choix.get(texte='4')
        self.mauvais = self.q.choix.get(texte='5')
        self.vf = Question.objects.create(quiz=self.quiz, texte='Le ciel est vert.', type_question='vf',
                                          points=Decimal('2'), penalite=Decimal('1'), ordre=2)
        self.vrai = Choix.objects.create(question=self.vf, texte='Vrai', est_correct=False, ordre=1)
        self.faux = Choix.objects.create(question=self.vf, texte='Faux', est_correct=True, ordre=2)

    def corriger(self, reponses):
        tentative = TentativeQuiz.objects.create(quiz=self.quiz, etudiant=self.a.etu, fin_prevue=timezone.now())
        for question, choix in reponses:
            reponse = ReponseQuiz.objects.create(tentative=tentative, question=question)
            reponse.choix_selectionnes.set(choix)
        corriger_tentative(tentative)
        tentative.refresh_from_db()
        return tentative

    def score(self, tentative, question):
        return tentative.reponses.get(question=question).score_obtenu

    def test_reponse_fausse_penalisee(self):
        t = self.corriger([(self.q, [self.mauvais]), (self.vf, [self.faux])])
        self.assertEqual(self.score(t, self.q), Decimal('-0.50'))
        self.assertEqual(self.score(t, self.vf), Decimal('2.00'))
        self.assertEqual(t.score, Decimal('1.50'))

    def test_absence_de_reponse_non_penalisee(self):
        t = self.corriger([(self.vf, [self.faux])])
        self.assertEqual(self.score(t, self.q), Decimal('0.00'))
        self.assertEqual(t.score, Decimal('2.00'))

    def test_reponse_juste(self):
        t = self.corriger([(self.q, [self.bon])])
        self.assertEqual(self.score(t, self.q), Decimal('1.00'))

    def test_total_jamais_negatif(self):
        t = self.corriger([(self.q, [self.mauvais]), (self.vf, [self.vrai])])
        self.assertEqual(self.score(t, self.vf), Decimal('-1.00'))
        self.assertEqual(t.score, Decimal('0.00'))
        self.assertEqual(t.score_max, Decimal('3.00'))


class PenaliteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.ens = client_for(self.a.ens)

    def enregistrer(self, question):
        return self.ens.patch(f'{Q}/quizzes/{self.quiz.id}/', {'questions': [question]}, format='json')

    def test_validation_de_la_penalite(self):
        courte = {'texte': 'Capitale ?', 'type_question': 'courte', 'points': '1', 'penalite': '0.5',
                  'choix': [{'texte': 'Paris', 'est_correct': True}]}
        self.assertEqual(self.enregistrer(courte).status_code, 400)
        par_choix = {'texte': 'Pairs ?', 'type_question': 'qcm', 'points': '1', 'mode_notation': 'par_choix',
                     'penalite': '0.5', 'choix': [{'texte': '2', 'est_correct': True, 'points': '1'},
                                                  {'texte': '3', 'est_correct': False, 'points': '0'}]}
        self.assertEqual(self.enregistrer(par_choix).status_code, 400)
        trop = {'texte': 'Vrai ?', 'type_question': 'vf', 'points': '1', 'penalite': '2',
                'choix': [{'texte': 'Vrai', 'est_correct': True}, {'texte': 'Faux', 'est_correct': False}]}
        self.assertEqual(self.enregistrer(trop).status_code, 400)
        negative = dict(trop, penalite='-1')
        self.assertEqual(self.enregistrer(negative).status_code, 400)
        ok = dict(trop, penalite='0.5', explication='Parce que.')
        res = self.enregistrer(ok)
        self.assertEqual(res.status_code, 200, res.data)
        question = self.quiz.questions.get()
        self.assertEqual(question.penalite, Decimal('0.50'))
        self.assertEqual(question.explication, 'Parce que.')

    def test_explication_reservee_au_corrige(self):
        q = self.a.question
        q.penalite = Decimal('0.5')
        q.explication = '2 + 2 font 4.'
        q.save()
        self.quiz.afficher_corrige = True
        self.quiz.save()
        etu = client_for(self.a.etu)
        res = etu.post(f'{Q}/quizzes/{self.quiz.id}/demarrer/')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['questions'][0]['penalite'], '0.50')
        self.assertNotIn('2 + 2 font 4.', json.dumps(res.data, default=str))
        tentative_id = res.data['id']
        mauvais = q.choix.get(texte='5')
        etu.put(f'{Q}/tentatives/{tentative_id}/repondre/', {'question': q.id, 'choix': [mauvais.id]}, format='json')
        res = etu.post(f'{Q}/tentatives/{tentative_id}/soumettre/')
        self.assertEqual(res.status_code, 200)
        corrige = res.data['corrige'][0]
        self.assertEqual(corrige['explication'], '2 + 2 font 4.')
        self.assertEqual(corrige['penalite'], '0.50')
        self.assertEqual(corrige['score_obtenu'], '-0.50')
        self.assertEqual(res.data['resultat']['score'], '0.00')
