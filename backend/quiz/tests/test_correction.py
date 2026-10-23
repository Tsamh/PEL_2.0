from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world
from quiz.correction import corriger_tentative, en_decimal, noter
from quiz.models import Choix, Question, ReponseQuiz, TentativeQuiz

D = Decimal


def creer_question(quiz, type_question='qcm', points='1', mode='tout_ou_rien', choix=()):
    question = Question.objects.create(
        quiz=quiz, texte='?', type_question=type_question, points=D(points), mode_notation=mode,
    )
    objets = [
        Choix.objects.create(question=question, texte=texte, est_correct=ok, points=D(pts), ordre=i)
        for i, (texte, ok, pts) in enumerate(choix, 1)
    ]
    return question, objets


class NoterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        cls.quiz = cls.w.a.quiz

    def test_qcm_mono(self):
        q, (bon, mauvais) = creer_question(self.quiz, choix=[('4', True, '0'), ('5', False, '0')])
        self.assertEqual(noter(q, [bon.id], ''), (D('1.00'), 'auto', 0.0))
        self.assertEqual(noter(q, [mauvais.id], '')[0], D('0.00'))
        self.assertEqual(noter(q, [], '')[0], D('0.00'))

    def test_qcm_multi_tout_ou_rien(self):
        q, (a, b, c) = creer_question(self.quiz, points='2', choix=[('a', True, '0'), ('b', True, '0'), ('c', False, '0')])
        self.assertEqual(noter(q, [a.id, b.id], '')[0], D('2.00'))
        self.assertEqual(noter(q, [a.id], '')[0], D('0.00'))
        self.assertEqual(noter(q, [a.id, b.id, c.id], '')[0], D('0.00'))

    def test_par_choix_points_negatifs_et_bornes(self):
        q, (a, b, c) = creer_question(
            self.quiz, mode='par_choix',
            choix=[('a', True, '0.5'), ('b', True, '0.5'), ('c', False, '-0.5')],
        )
        self.assertEqual(noter(q, [a.id], '')[0], D('0.50'))
        self.assertEqual(noter(q, [a.id, b.id], '')[0], D('1.00'))
        self.assertEqual(noter(q, [a.id, c.id], '')[0], D('0.00'))
        self.assertEqual(noter(q, [c.id], '')[0], D('0.00'))
        self.assertEqual(noter(q, [a.id, b.id, c.id], '')[0], D('0.50'))

    def test_vrai_faux(self):
        q, (vrai, faux) = creer_question(self.quiz, 'vf', choix=[('Vrai', False, '0'), ('Faux', True, '0')])
        self.assertEqual(noter(q, [faux.id], '')[0], D('1.00'))
        self.assertEqual(noter(q, [vrai.id], '')[0], D('0.00'))

    def test_courte_suggestion_a_valider(self):
        q, _ = creer_question(self.quiz, 'courte', '2', choix=[('Paris', True, '0'), ('Paname', True, '0')])
        self.assertEqual(noter(q, [], 'paris '), (D('2.00'), 'a_valider', 1.0))
        score, statut, similarite = noter(q, [], 'Lyon')
        self.assertEqual((score, statut), (D('0.00'), 'a_valider'))
        self.assertLess(similarite, 0.8)

    def test_courte_vide_reste_automatique(self):
        q, _ = creer_question(self.quiz, 'courte', choix=[('Paris', True, '0')])
        self.assertEqual(noter(q, [], '   '), (D('0.00'), 'auto', 0.0))

    def test_en_decimal(self):
        self.assertEqual(en_decimal('1.5'), D('1.5'))
        self.assertEqual(en_decimal(2), D('2'))
        for valeur in (True, 'abc', 'NaN', 'Infinity', None, [1]):
            with self.subTest(valeur=valeur):
                self.assertIsNone(en_decimal(valeur))


class CorrigerTentativeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def nouvelle_tentative(self):
        a = self.w.a
        return TentativeQuiz.objects.create(quiz=a.quiz, etudiant=a.etu, fin_prevue=timezone.now())

    def test_somme_et_note_provisoire(self):
        a = self.w.a
        courte, _ = creer_question(a.quiz, 'courte', '2', choix=[('Paris', True, '0')])
        tentative = self.nouvelle_tentative()
        reponse = ReponseQuiz.objects.create(tentative=tentative, question=a.question)
        reponse.choix_selectionnes.set([a.question.choix.get(texte='4')])
        ReponseQuiz.objects.create(tentative=tentative, question=courte, texte_reponse='Paris')
        corriger_tentative(tentative)
        tentative.refresh_from_db()
        self.assertEqual(tentative.score, D('3.00'))
        self.assertEqual(tentative.score_max, D('3.00'))
        self.assertTrue(tentative.est_provisoire)

    def test_question_sans_reponse_vaut_zero(self):
        tentative = self.nouvelle_tentative()
        corriger_tentative(tentative)
        tentative.refresh_from_db()
        self.assertEqual(tentative.reponses.count(), 1)
        self.assertEqual(tentative.score, D('0.00'))
        self.assertEqual(tentative.score_max, D('1.00'))

    def test_reponse_validee_non_recorrigee(self):
        a = self.w.a
        tentative = self.nouvelle_tentative()
        reponse = ReponseQuiz.objects.create(
            tentative=tentative, question=a.question, statut_correction=ReponseQuiz.VALIDEE, score_obtenu=D('0'),
        )
        reponse.choix_selectionnes.set([a.question.choix.get(texte='4')])
        corriger_tentative(tentative)
        reponse.refresh_from_db()
        self.assertEqual(reponse.score_obtenu, D('0.00'))
