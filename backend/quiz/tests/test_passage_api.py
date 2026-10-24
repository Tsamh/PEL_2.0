import json
from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from quiz.models import Quiz, TentativeQuiz
from referentiel.models import Inscription

Q = '/api/quiz'


class PassageApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.client_etu = client_for(self.a.etu)
        self.bon = self.a.question.choix.get(texte='4')
        self.mauvais = self.a.question.choix.get(texte='5')

    def demarrer(self, client=None, quiz=None):
        return (client or self.client_etu).post(f'{Q}/quizzes/{(quiz or self.quiz).id}/demarrer/')

    def repondre(self, tentative_id, choix, client=None):
        corps = {'question': self.a.question.id, 'choix': choix}
        return (client or self.client_etu).put(f'{Q}/tentatives/{tentative_id}/repondre/', corps, format='json')

    def soumettre(self, tentative_id):
        return self.client_etu.post(f'{Q}/tentatives/{tentative_id}/soumettre/')

    def test_demarrer_sans_bonnes_reponses(self):
        res = self.demarrer()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(res.data['questions']), 1)
        self.assertFalse(res.data['questions'][0]['est_multiple'])
        self.assertNotIn('est_correct', json.dumps(res.data, default=str))
        self.assertIsNotNone(res.data['heure_serveur'])
        self.assertIsNone(res.data['resultat'])
        self.assertTrue(AuditLog.objects.filter(action='demarrage_quiz').exists())

    def test_reprise_renvoie_la_meme_tentative_et_les_reponses(self):
        tentative_id = self.demarrer().data['id']
        self.assertEqual(self.repondre(tentative_id, [self.bon.id]).status_code, 200)
        res = self.demarrer()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['id'], tentative_id)
        self.assertEqual(res.data['reponses'], [{'question': self.a.question.id, 'choix': [self.bon.id], 'texte': ''}])

    def test_soumission_complete(self):
        tentative_id = self.demarrer().data['id']
        self.repondre(tentative_id, [self.bon.id])
        with self.captureOnCommitCallbacks(execute=True):
            res = self.soumettre(tentative_id)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['statut'], 'soumise')
        self.assertEqual(res.data['resultat'], {'score': '1.00', 'score_max': '1.00', 'provisoire': False})
        self.assertEqual(res.data['questions'], [])
        self.assertEqual(len(mail.outbox), 1)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.soumettre(tentative_id).status_code, 409)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.repondre(tentative_id, [self.bon.id]).status_code, 409)
        self.assertEqual(self.demarrer().status_code, 409)

    def test_entrees_invalides(self):
        tentative_id = self.demarrer().data['id']
        url = f'{Q}/tentatives/{tentative_id}/repondre/'
        cas = [
            {'question': self.w.b.question.id, 'choix': []},
            {'question': 'abc', 'choix': []},
            {'question': self.a.question.id, 'choix': 'abc'},
            {'question': self.a.question.id, 'choix': [self.bon.id, self.mauvais.id]},
            {'question': self.a.question.id, 'choix': [self.w.b.question.choix.first().id]},
        ]
        for corps in cas:
            with self.subTest(corps=corps):
                self.assertEqual(self.client_etu.put(url, corps, format='json').status_code, 400)

    def test_tentatives_multiples_et_meilleure_note(self):
        Quiz.objects.filter(pk=self.quiz.pk).update(tentatives_autorisees=2)
        premiere = self.demarrer().data['id']
        self.repondre(premiere, [self.bon.id])
        self.soumettre(premiere)
        seconde = self.demarrer().data['id']
        self.repondre(seconde, [self.mauvais.id])
        self.soumettre(seconde)
        etat = self.client_etu.get(f'{Q}/quizzes/{self.quiz.id}/').data['etat']
        self.assertEqual(etat['tentatives_utilisees'], 2)
        self.assertEqual(etat['tentatives_restantes'], 0)
        self.assertEqual(etat['derniere_tentative'], seconde)
        self.assertEqual(etat['meilleure_note'], {'score': '1.00', 'score_max': '1.00', 'provisoire': False})

    def test_fenetre(self):
        maintenant = timezone.now()
        Quiz.objects.filter(pk=self.quiz.pk).update(date_debut=maintenant + timedelta(hours=1))
        self.assertEqual(self.demarrer().status_code, 409)
        Quiz.objects.filter(pk=self.quiz.pk).update(date_debut=None, date_fin=maintenant - timedelta(minutes=1))
        self.assertEqual(self.demarrer().status_code, 409)
        self.assertFalse(self.client_etu.get(f'{Q}/quizzes/{self.quiz.id}/').data['etat']['ouvert'])

    def test_quiz_invisible(self):
        self.assertEqual(self.demarrer(quiz=self.w.b.quiz).status_code, 404)
        Quiz.objects.filter(pk=self.quiz.pk).update(est_publie=False)
        self.assertEqual(self.demarrer().status_code, 404)

    def test_expiration(self):
        tentative_id = self.demarrer().data['id']
        TentativeQuiz.objects.filter(pk=tentative_id).update(fin_prevue=timezone.now() - timedelta(minutes=2))
        self.assertEqual(self.repondre(tentative_id, [self.bon.id]).status_code, 409)
        res = self.client_etu.get(f'{Q}/tentatives/{tentative_id}/')
        self.assertEqual(res.data['statut'], 'soumise')
        self.assertTrue(res.data['soumission_auto'])

    def test_soumettre_apres_expiration(self):
        tentative_id = self.demarrer().data['id']
        TentativeQuiz.objects.filter(pk=tentative_id).update(fin_prevue=timezone.now() - timedelta(minutes=2))
        res = self.soumettre(tentative_id)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['soumission_auto'])

    def test_publication_differee(self):
        Quiz.objects.filter(pk=self.quiz.pk).update(publication_resultats='differee')
        tentative_id = self.demarrer().data['id']
        self.assertIsNone(self.soumettre(tentative_id).data['resultat'])
        self.assertIsNone(self.client_etu.get(f'{Q}/quizzes/{self.quiz.id}/').data['etat']['meilleure_note'])
        Quiz.objects.filter(pk=self.quiz.pk).update(resultats_publies=True)
        self.assertIsNotNone(self.client_etu.get(f'{Q}/tentatives/{tentative_id}/').data['resultat'])

    def test_corrige_masque_tant_qu_il_reste_des_tentatives(self):
        Quiz.objects.filter(pk=self.quiz.pk).update(tentatives_autorisees=2, afficher_corrige=True)
        premiere = self.demarrer().data['id']
        self.assertIsNone(self.soumettre(premiere).data['corrige'])
        seconde = self.demarrer().data['id']
        corrige = self.soumettre(seconde).data['corrige']
        self.assertEqual(len(corrige), 1)
        self.assertEqual({c['texte'] for c in corrige[0]['choix'] if c['est_correct']}, {'4'})

    def test_liste_quiz_etudiant_sans_questions(self):
        res = self.client_etu.get(f'{Q}/quizzes/')
        quiz = res.data['results'][0]
        self.assertNotIn('questions', quiz)
        self.assertEqual(quiz['nb_questions'], 1)
        self.assertEqual(quiz['etat']['tentatives_restantes'], 1)
        self.assertIsNone(quiz['etat']['tentative_en_cours'])

    def test_tentative_d_un_autre_etudiant(self):
        tentative_id = self.demarrer().data['id']
        autre = make_user('etu2A', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=autre, classe=self.a.classe)
        client_autre = client_for(autre)
        self.assertEqual(client_autre.get(f'{Q}/tentatives/{tentative_id}/').status_code, 404)
        self.assertEqual(self.repondre(tentative_id, [self.bon.id], client=client_autre).status_code, 404)
        self.assertEqual(client_autre.get(f'{Q}/tentatives/').data['count'], 0)

    def test_seuls_les_etudiants_passent(self):
        for user in (self.a.ens, self.a.admin):
            with self.subTest(role=user.role):
                self.assertEqual(self.demarrer(client=client_for(user)).status_code, 403)
                self.assertEqual(client_for(user).get(f'{Q}/tentatives/').status_code, 403)
