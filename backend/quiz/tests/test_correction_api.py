from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from quiz import passage
from quiz.models import Choix, Question, Quiz, ReponseQuiz, TentativeQuiz

Q = '/api/quiz'


class CorrectionApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.courte = Question.objects.create(quiz=a.quiz, texte='Capitale ?', type_question='courte', points=2, ordre=2)
        Choix.objects.create(question=cls.courte, texte='Paris', est_correct=True)

    def setUp(self):
        a = self.w.a
        self.tentative, _ = passage.demarrer(a.quiz, a.etu)
        passage.enregistrer_reponse(self.tentative, {'question': a.question.id, 'choix': [a.question.choix.get(texte='4').id]})
        passage.enregistrer_reponse(self.tentative, {'question': self.courte.id, 'texte': 'paris'})
        passage.soumettre(self.tentative)
        self.reponse = ReponseQuiz.objects.get(tentative=self.tentative, question=self.courte)

    def valider(self, user, score, reponse=None):
        reponse = reponse or self.reponse
        return client_for(user).post(f'{Q}/reponses/{reponse.id}/valider/', {'score': score}, format='json')

    def test_liste_des_tentatives(self):
        a = self.w.a
        res = client_for(a.ens).get(f'{Q}/quizzes/{a.quiz.id}/tentatives/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        ligne = res.data[0]
        self.assertEqual((ligne['score'], ligne['score_max']), ('3.00', '3.00'))
        self.assertTrue(ligne['est_provisoire'])
        self.assertEqual(ligne['nb_a_valider'], 1)
        self.assertTrue(ligne['est_meilleure'])

    def test_la_liste_cloture_les_tentatives_expirees(self):
        b = self.w.b
        tentative, _ = passage.demarrer(b.quiz, b.etu)
        TentativeQuiz.objects.filter(pk=tentative.pk).update(fin_prevue=timezone.now() - timedelta(minutes=5))
        client_for(b.ens).get(f'{Q}/quizzes/{b.quiz.id}/tentatives/')
        tentative.refresh_from_db()
        self.assertEqual(tentative.statut, 'soumise')

    def test_file_de_validation(self):
        a = self.w.a
        res = client_for(a.ens).get(f'{Q}/reponses/', {'quiz': a.quiz.id, 'statut': 'a_valider'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)
        item = res.data['results'][0]
        self.assertEqual(item['reponses_acceptees'], ['Paris'])
        self.assertEqual(item['score_obtenu'], '2.00')
        self.assertEqual(item['texte_reponse'], 'paris')
        self.assertEqual(client_for(a.ens).get(f'{Q}/reponses/', {'quiz': 'abc'}).data['count'], 0)

    def test_valider_recalcule_et_journalise(self):
        res = self.valider(self.w.a.ens, '1.5')
        self.assertEqual(res.status_code, 200, res.data)
        self.tentative.refresh_from_db()
        self.assertEqual(self.tentative.score, Decimal('2.50'))
        self.assertFalse(self.tentative.est_provisoire)
        entree = AuditLog.objects.get(action='validation_reponse')
        self.assertEqual((entree.details['avant'], entree.details['apres']), ('2.00', '1.50'))
        self.assertEqual(entree.etablissement, self.w.a.etab)

    def test_valider_bornes(self):
        for score in ('-1', '3', 'abc', None, True, '1E+999999', '-1E+999999', 'NaN', 'Infinity', '1e999', [1], {'a': 1}):
            with self.subTest(score=score):
                self.assertEqual(self.valider(self.w.a.ens, score).status_code, 400)
        self.reponse.refresh_from_db()
        self.assertEqual(self.reponse.statut_correction, ReponseQuiz.A_VALIDER)
        self.assertEqual(self.reponse.score_obtenu, Decimal('2.00'))
        self.assertFalse(AuditLog.objects.filter(action='validation_reponse').exists())

    def test_corps_non_objet_renvoie_400(self):
        url = f'{Q}/reponses/{self.reponse.id}/valider/'
        for corps in ([1], 'abc', 5):
            with self.subTest(corps=corps):
                res = client_for(self.w.a.ens).post(url, corps, format='json')
                self.assertEqual(res.status_code, 400)

    def test_valider_exposant_minuscule_ne_plante_pas(self):
        res = self.valider(self.w.a.ens, '1E-999999')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['score_obtenu'], '0.00')

    def test_seules_les_reponses_courtes_soumises_sont_validables(self):
        qcm = ReponseQuiz.objects.get(tentative=self.tentative, question=self.w.a.question)
        self.assertEqual(self.valider(self.w.a.ens, '1', reponse=qcm).status_code, 404)

    def test_perimetre(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(client_for(b.ens).get(f'{Q}/reponses/').data['count'], 0)
        self.assertEqual(self.valider(b.ens, '1').status_code, 404)
        self.assertEqual(self.valider(b.admin, '1').status_code, 404)
        self.assertEqual(client_for(b.ens).get(f'{Q}/quizzes/{a.quiz.id}/tentatives/').status_code, 404)
        self.assertEqual(self.valider(a.admin, '1').status_code, 200)

    def test_etudiant_refuse(self):
        a = self.w.a
        client = client_for(a.etu)
        self.assertEqual(client.get(f'{Q}/reponses/').status_code, 403)
        self.assertEqual(client.get(f'{Q}/quizzes/{a.quiz.id}/tentatives/').status_code, 403)
        self.assertEqual(client.post(f'{Q}/quizzes/{a.quiz.id}/publier_resultats/').status_code, 403)
        self.assertEqual(self.valider(a.etu, '1').status_code, 403)

    def test_publier_resultats(self):
        a = self.w.a
        client = client_for(a.ens)
        url = f'{Q}/quizzes/{a.quiz.id}/publier_resultats/'
        self.assertEqual(client.post(url).status_code, 409)
        Quiz.objects.filter(pk=a.quiz.pk).update(publication_resultats='differee')
        self.assertEqual(client.post(url).status_code, 200)
        self.assertTrue(Quiz.objects.get(pk=a.quiz.pk).resultats_publies)
        self.assertTrue(AuditLog.objects.filter(action='publication_resultats').exists())
        self.assertEqual(client.post(url).status_code, 409)
