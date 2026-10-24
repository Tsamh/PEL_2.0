from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.testing import build_world
from audit.models import AuditLog
from quiz import passage
from quiz.exceptions import Conflit
from quiz.models import Question, TentativeQuiz


class PassageServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.bon = self.a.question.choix.get(texte='4')
        self.mauvais = self.a.question.choix.get(texte='5')

    def expirer(self, tentative, secondes=60):
        TentativeQuiz.objects.filter(pk=tentative.pk).update(fin_prevue=timezone.now() - timedelta(seconds=secondes))
        tentative.refresh_from_db()

    def test_fin_prevue_bornee_par_la_fenetre(self):
        debut = timezone.now()
        self.assertEqual(passage.calculer_fin_prevue(self.quiz, debut), debut + timedelta(minutes=30))
        self.quiz.date_fin = debut + timedelta(minutes=5)
        self.assertEqual(passage.calculer_fin_prevue(self.quiz, debut), self.quiz.date_fin)

    def test_demarrer_puis_reprendre(self):
        tentative, creee = passage.demarrer(self.quiz, self.a.etu)
        self.assertTrue(creee)
        self.assertEqual((tentative.numero, tentative.statut), (1, 'en_cours'))
        meme, creee = passage.demarrer(self.quiz, self.a.etu)
        self.assertEqual((meme.pk, creee), (tentative.pk, False))

    def test_reprise_interdite_soumet_l_ancienne(self):
        self.quiz.reprise_autorisee = False
        self.quiz.tentatives_autorisees = 2
        self.quiz.save()
        premiere, _ = passage.demarrer(self.quiz, self.a.etu)
        seconde, creee = passage.demarrer(self.quiz, self.a.etu)
        premiere.refresh_from_db()
        self.assertTrue(creee)
        self.assertEqual(seconde.numero, 2)
        self.assertEqual(premiere.statut, 'soumise')
        self.assertTrue(premiere.soumission_auto)
        with self.assertRaises(Conflit):
            passage.demarrer(self.quiz, self.a.etu)
        seconde.refresh_from_db()
        self.assertEqual(seconde.statut, 'soumise')

    def test_fenetre_et_limite(self):
        self.quiz.date_debut = timezone.now() + timedelta(hours=1)
        with self.assertRaises(Conflit):
            passage.demarrer(self.quiz, self.a.etu)
        self.quiz.date_debut = None
        self.quiz.date_fin = timezone.now() - timedelta(minutes=1)
        with self.assertRaises(Conflit):
            passage.demarrer(self.quiz, self.a.etu)
        self.quiz.date_fin = None
        tentative, _ = passage.demarrer(self.quiz, self.a.etu)
        passage.soumettre(tentative)
        with self.assertRaises(Conflit):
            passage.demarrer(self.quiz, self.a.etu)

    def test_enregistrer_reponse_remplace(self):
        tentative, _ = passage.demarrer(self.quiz, self.a.etu)
        passage.enregistrer_reponse(tentative, {'question': self.a.question.id, 'choix': [self.mauvais.id]})
        reponse = passage.enregistrer_reponse(tentative, {'question': str(self.a.question.id), 'choix': [self.bon.id]})
        self.assertEqual(tentative.reponses.count(), 1)
        self.assertEqual(list(reponse.choix_selectionnes.values_list('id', flat=True)), [self.bon.id])

    def test_enregistrer_reponse_invalide(self):
        tentative, _ = passage.demarrer(self.quiz, self.a.etu)
        autre = self.w.b.question
        cas = [
            {'question': autre.id, 'choix': []},
            {'question': 'x'},
            {'question': self.a.question.id, 'choix': [autre.choix.first().id]},
            {'question': self.a.question.id, 'choix': 'abc'},
            {'question': self.a.question.id, 'choix': [True]},
            {'question': self.a.question.id, 'choix': [self.bon.id, self.mauvais.id]},
            {'question': self.a.question.id, 'choix': [], 'texte': 12},
        ]
        for data in cas:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    passage.enregistrer_reponse(tentative, data)

    def test_expiration_et_tolerance(self):
        tentative, _ = passage.demarrer(self.quiz, self.a.etu)
        self.expirer(tentative, secondes=10)
        passage.enregistrer_reponse(tentative, {'question': self.a.question.id, 'choix': [self.bon.id]})
        self.expirer(tentative, secondes=60)
        with self.assertRaises(Conflit):
            passage.enregistrer_reponse(tentative, {'question': self.a.question.id, 'choix': [self.bon.id]})
        tentative.refresh_from_db()
        self.assertEqual(tentative.statut, 'soumise')
        self.assertTrue(tentative.soumission_auto)
        self.assertEqual(tentative.score, Decimal('1.00'))

    def test_soumettre_idempotent_un_seul_mail(self):
        tentative, _ = passage.demarrer(self.quiz, self.a.etu)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(passage.soumettre(tentative))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(passage.soumettre(tentative))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.quiz.titre, mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [self.a.etu.email])
        self.assertEqual(AuditLog.objects.filter(action='soumission_quiz').count(), 1)
        self.assertEqual(AuditLog.objects.get(action='soumission_quiz').etablissement, self.a.etab)

    def test_cloturer_expirees_et_commande(self):
        tentative, _ = passage.demarrer(self.quiz, self.a.etu)
        en_cours, _ = passage.demarrer(self.w.b.quiz, self.w.b.etu)
        self.expirer(tentative)
        sortie = StringIO()
        call_command('cloturer_tentatives', stdout=sortie)
        self.assertIn('1 tentative(s)', sortie.getvalue())
        tentative.refresh_from_db()
        en_cours.refresh_from_db()
        self.assertEqual((tentative.statut, en_cours.statut), ('soumise', 'en_cours'))

    def test_cloturer_expirees_continue_apres_une_erreur(self):
        premiere, _ = passage.demarrer(self.quiz, self.a.etu)
        seconde, _ = passage.demarrer(self.w.b.quiz, self.w.b.etu)
        self.expirer(premiere)
        self.expirer(seconde)
        original = passage.soumettre

        def soumettre(tentative, **kwargs):
            if tentative.pk == premiere.pk:
                raise RuntimeError('panne simulée')
            return original(tentative, **kwargs)

        with mock.patch.object(passage, 'soumettre', side_effect=soumettre),                 self.assertLogs('quiz.passage', level='ERROR'):
            self.assertEqual(passage.cloturer_expirees(), 1)
        premiere.refresh_from_db()
        seconde.refresh_from_db()
        self.assertEqual((premiere.statut, seconde.statut), ('en_cours', 'soumise'))

    def test_visibilite(self):
        self.quiz.tentatives_autorisees = 2
        self.quiz.afficher_corrige = True
        self.quiz.save()
        tentative, _ = passage.demarrer(self.quiz, self.a.etu)
        self.assertFalse(passage.corrige_visible(tentative))
        passage.soumettre(tentative)
        self.assertTrue(passage.score_visible(self.quiz))
        self.assertFalse(passage.corrige_visible(tentative))
        seconde, _ = passage.demarrer(self.quiz, self.a.etu)
        passage.soumettre(seconde)
        self.assertTrue(passage.corrige_visible(tentative))
        self.quiz.publication_resultats = 'differee'
        self.quiz.save()
        tentative.refresh_from_db()
        self.assertFalse(passage.score_visible(self.quiz))
        self.assertFalse(passage.corrige_visible(tentative))

    def test_meilleure_tentative(self):
        self.quiz.tentatives_autorisees = 2
        self.quiz.save()
        premiere, _ = passage.demarrer(self.quiz, self.a.etu)
        passage.enregistrer_reponse(premiere, {'question': self.a.question.id, 'choix': [self.bon.id]})
        passage.soumettre(premiere)
        seconde, _ = passage.demarrer(self.quiz, self.a.etu)
        passage.soumettre(seconde)
        self.assertEqual(passage.meilleure_tentative(self.quiz.tentatives.all()).pk, premiere.pk)
        self.assertIsNone(passage.meilleure_tentative([]))
