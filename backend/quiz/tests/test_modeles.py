from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world
from quiz.models import Question, TentativeQuiz, ReponseQuiz


class ModelesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_reglages_par_defaut(self):
        quiz = self.w.a.quiz
        self.assertEqual(quiz.tentatives_autorisees, 1)
        self.assertTrue(quiz.reprise_autorisee)
        self.assertEqual(quiz.publication_resultats, 'immediate')
        self.assertFalse(quiz.resultats_publies)
        self.assertFalse(quiz.afficher_corrige)

    def test_points_decimaux_et_mode_par_defaut(self):
        question = Question.objects.create(quiz=self.w.a.quiz, texte='?', points=Decimal('1.5'))
        question.refresh_from_db()
        self.assertEqual(question.points, Decimal('1.50'))
        self.assertEqual(question.mode_notation, 'tout_ou_rien')

    def test_est_multiple(self):
        question = self.w.a.question
        self.assertFalse(question.est_multiple)
        question.choix.filter(texte='5').update(est_correct=True)
        self.assertTrue(Question.objects.get(pk=question.pk).est_multiple)

    def test_plusieurs_tentatives_numero_unique(self):
        a = self.w.a
        maintenant = timezone.now()
        TentativeQuiz.objects.create(quiz=a.quiz, etudiant=a.etu, numero=1, fin_prevue=maintenant)
        TentativeQuiz.objects.create(quiz=a.quiz, etudiant=a.etu, numero=2, fin_prevue=maintenant)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TentativeQuiz.objects.create(quiz=a.quiz, etudiant=a.etu, numero=2, fin_prevue=maintenant)
        self.assertEqual(a.etu.tentatives_quiz.count(), 2)

    def test_reponse_multi_choix_et_note_provisoire(self):
        a = self.w.a
        tentative = TentativeQuiz.objects.create(quiz=a.quiz, etudiant=a.etu, fin_prevue=timezone.now())
        self.assertEqual(tentative.statut, 'en_cours')
        reponse = ReponseQuiz.objects.create(tentative=tentative, question=a.question)
        reponse.choix_selectionnes.set(a.question.choix.all())
        self.assertEqual(reponse.choix_selectionnes.count(), 2)
        self.assertFalse(tentative.est_provisoire)
        reponse.statut_correction = ReponseQuiz.A_VALIDER
        reponse.save()
        self.assertTrue(TentativeQuiz.objects.get(pk=tentative.pk).est_provisoire)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReponseQuiz.objects.create(tentative=tentative, question=a.question)

    def test_etablissement_et_duree(self):
        a = self.w.a
        debut = timezone.now()
        tentative = TentativeQuiz.objects.create(
            quiz=a.quiz, etudiant=a.etu, debut=debut, fin_prevue=debut,
            soumise_le=debut + timedelta(seconds=95),
        )
        self.assertEqual(a.quiz.etablissement, a.etab)
        self.assertEqual(tentative.etablissement, a.etab)
        self.assertEqual(tentative.duree_secondes, 95)
