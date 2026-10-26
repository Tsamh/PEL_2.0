from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for
from quiz.models import Choix, Question, Quiz, ReponseQuiz, SessionQuiz, TentativeQuiz
from referentiel.models import AnneeAcademique

Q = '/api/quiz'


def ids(res):
    data = res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data
    return [l['id'] if 'id' in l else l['quiz'] for l in data]


class ArchivageQuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.quiz = a.quiz
        cls.sans_annee = Quiz.objects.create(titre='Sans année', filiere=a.filiere, est_publie=True, cree_par=a.ens)
        cls.sans_annee.classes.add(a.classe)
        cls.courte = Question.objects.create(quiz=cls.quiz, texte='Capitale ?', type_question='courte', points=1, ordre=2)
        cls.q_libre = Question.objects.create(quiz=cls.sans_annee, texte='Libre ?', type_question='qcm', points=1, ordre=1)
        cls.choix_libre = Choix.objects.create(question=cls.q_libre, texte='A', est_correct=True)
        cls.tentative = TentativeQuiz.objects.create(quiz=cls.quiz, etudiant=a.etu, numero=1,
                                                     fin_prevue=timezone.now() + timedelta(days=30))
        cls.session = SessionQuiz.objects.create(quiz=cls.quiz, ouverture=timezone.now(),
                                                 fermeture=timezone.now() + timedelta(hours=1))
        TentativeQuiz.objects.filter(pk=cls.tentative.pk).update(statut=TentativeQuiz.SOUMISE, soumise_le=timezone.now())
        cls.reponse = ReponseQuiz.objects.create(tentative=cls.tentative, question=cls.courte, texte_reponse='Paris',
                                                 statut_correction=ReponseQuiz.A_VALIDER)
        AnneeAcademique.objects.filter(pk=a.annee.pk).update(archivee=True)

    def setUp(self):
        self.a = self.w.a

    def test_listes(self):
        for user in (self.a.admin, self.a.ens, self.a.etu):
            with self.subTest(role=user.role):
                c = client_for(user)
                self.assertNotIn(self.quiz.pk, ids(c.get(f'{Q}/quizzes/')))
                self.assertIn(self.sans_annee.pk, ids(c.get(f'{Q}/quizzes/')))
                self.assertEqual(ids(c.get(f'{Q}/quizzes/', {'archives': '1'})), [self.quiz.pk])
        self.assertNotIn(self.quiz.pk, ids(client_for(self.a.ens).get(f'{Q}/quizzes/statistiques/')))
        self.assertIn(self.quiz.pk, ids(client_for(self.a.ens).get(f'{Q}/quizzes/statistiques/', {'archives': '1'})))
        self.assertEqual(ids(client_for(self.a.etu).get(f'{Q}/tentatives/')), [])
        self.assertEqual(ids(client_for(self.a.etu).get(f'{Q}/tentatives/', {'archives': '1'})), [self.tentative.pk])
        self.assertEqual(ids(client_for(self.a.ens).get(f'{Q}/reponses/')), [])
        self.assertNotIn(self.session.pk, ids(client_for(self.a.ens).get(f'{Q}/sessions-quiz/')))

    def test_droits_sur_les_archives(self):
        self.assertEqual(ids(client_for(self.w.b.admin).get(f'{Q}/quizzes/', {'archives': '1'})), [])
        self.assertEqual(client_for(self.w.b.admin).get(f'{Q}/quizzes/{self.quiz.pk}/').status_code, 404)

    def test_consultation(self):
        c = client_for(self.a.ens)
        self.assertEqual(c.get(f'{Q}/quizzes/{self.quiz.pk}/').status_code, 200)
        self.assertEqual(c.get(f'{Q}/quizzes/{self.quiz.pk}/statistiques/').status_code, 200)
        self.assertEqual(client_for(self.a.etu).get(f'{Q}/tentatives/{self.tentative.pk}/').status_code, 200)

    def test_ecritures_refusees(self):
        c = client_for(self.a.ens)
        g = client_for(self.a.admin)
        cas = [
            c.patch(f'{Q}/quizzes/{self.quiz.pk}/', {'titre': 'X'}, format='json'),
            c.delete(f'{Q}/quizzes/{self.quiz.pk}/'),
            c.post(f'{Q}/quizzes/', {'titre': 'Nouveau', 'filiere': self.a.filiere.pk,
                                     'annee_academique': self.a.annee.pk}, format='json'),
            c.patch(f'{Q}/quizzes/{self.sans_annee.pk}/', {'annee_academique': self.a.annee.pk}, format='json'),
            c.patch(f'{Q}/questions/{self.a.question.pk}/', {'texte': 'X'}, format='json'),
            c.post(f'{Q}/questions/', {'quiz': self.quiz.pk, 'texte': 'Y', 'type_question': 'vf'}, format='json'),
            c.patch(f'{Q}/choix/{self.a.question.choix.first().pk}/', {'texte': 'X'}, format='json'),
            c.patch(f'{Q}/sessions-quiz/{self.session.pk}/', {'libelle': 'X'}, format='json'),
            c.post(f'{Q}/quizzes/{self.quiz.pk}/soumettre_validation/'),
            g.post(f'{Q}/quizzes/{self.quiz.pk}/valider/'),
            g.post(f'{Q}/quizzes/{self.quiz.pk}/refuser/', {'motif': 'Non'}, format='json'),
            c.post(f'{Q}/quizzes/{self.quiz.pk}/publier_resultats/'),
            c.post(f'{Q}/quizzes/{self.quiz.pk}/code_acces/'),
            c.delete(f'{Q}/quizzes/{self.quiz.pk}/code_acces/'),
            c.patch(f'{Q}/questions/{self.q_libre.pk}/', {'quiz': self.quiz.pk}, format='json'),
            c.patch(f'{Q}/questions/{self.a.question.pk}/', {'quiz': self.sans_annee.pk}, format='json'),
            c.post(f'{Q}/choix/', {'question': self.a.question.pk, 'texte': 'Z', 'est_correct': False}, format='json'),
            c.patch(f'{Q}/choix/{self.choix_libre.pk}/', {'question': self.a.question.pk}, format='json'),
            c.post(f'{Q}/sessions-quiz/', {'quiz': self.quiz.pk, 'classes': [self.a.classe.pk], 'ouverture': timezone.now().isoformat(),
                                           'fermeture': (timezone.now() + timedelta(hours=2)).isoformat()}, format='json'),
            c.patch(f'{Q}/quizzes/{self.quiz.pk}/', {'questions': [{'texte': 'N', 'type_question': 'vf'}]}, format='json'),
            c.post(f'{Q}/reponses/{self.reponse.pk}/valider/', {'score': 1}, format='json'),
            client_for(self.a.etu).post(f'{Q}/quizzes/{self.quiz.pk}/demarrer/'),
            client_for(self.a.etu).put(f'{Q}/tentatives/{self.tentative.pk}/repondre/', {}, format='json'),
            client_for(self.a.etu).post(f'{Q}/tentatives/{self.tentative.pk}/soumettre/'),
        ]
        for i, res in enumerate(cas):
            with self.subTest(cas=i):
                self.assertEqual(res.status_code, 409, getattr(res, 'data', None))
                self.assertIn('est archivée', str(res.data['detail']))
        self.assertEqual(Quiz.objects.get(pk=self.sans_annee.pk).annee_academique_id, None)

    def test_quiz_sans_annee_modifiable(self):
        res = client_for(self.a.ens).patch(f'{Q}/quizzes/{self.sans_annee.pk}/', {'titre': 'Libre'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)

    def test_suivi_global(self):
        res = client_for(self.a.admin).get(f'{Q}/suivi/', {'regroupement': 'classe'})
        self.assertEqual(res.data['total']['nb_evaluations'], 1)
        evals = client_for(self.a.admin).get(f'{Q}/suivi/evaluations/').data
        self.assertEqual([e['quiz'] for e in evals], [self.sans_annee.pk])
        res = client_for(self.a.admin).get(f'{Q}/suivi/', {'regroupement': 'classe', 'archives': '1'})
        self.assertEqual(res.data['total']['nb_evaluations'], 1)
        self.assertEqual(client_for(self.a.admin).get(f'{Q}/suivi/evaluations/', {'archives': '1'}).data[0]['quiz'],
                         self.quiz.pk)

    def test_desarchivage_retablit_l_ecriture(self):
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=False)
        res = client_for(self.a.ens).patch(f'{Q}/quizzes/{self.quiz.pk}/', {'titre': 'Rouvert'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
