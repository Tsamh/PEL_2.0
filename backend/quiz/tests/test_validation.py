import importlib

from django.apps import apps
from django.test import TestCase

from accounts.testing import build_world, client_for
from quiz.models import Quiz

Q = '/api/quiz/quizzes'
QUESTION = {'texte': '2 + 2 ?', 'type_question': 'qcm', 'points': '1',
            'choix': [{'texte': '4', 'est_correct': True}, {'texte': '5', 'est_correct': False}]}
MESSAGE = "La publication de ce quiz demande la validation du responsable de formation."


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.ens = client_for(self.a.ens)
        self.resp = client_for(self.a.resp)

    def activer(self, valeur=True):
        self.a.etab.validation_quiz_requise = valeur
        self.a.etab.save()

    def creer(self, client=None, **extra):
        corps = {'titre': 'Quiz à valider', 'filiere': self.a.filiere.id, 'questions': [QUESTION], **extra}
        return (client or self.ens).post(f'{Q}/', corps, format='json')

    def patch(self, quiz_id, corps, client=None):
        return (client or self.ens).patch(f'{Q}/{quiz_id}/', corps, format='json')

    def valider_en_base(self, quiz_id, publie=True):
        Quiz.objects.filter(pk=quiz_id).update(statut_validation=Quiz.VALIDEE, est_publie=publie)


class ReglesPublicationTests(Base):
    def test_sans_reglage_rien_ne_change(self):
        res = self.creer(est_publie=True)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data['est_publie'])
        self.assertFalse(res.data['validation_requise'])

    def test_publication_directe_refusee(self):
        self.activer()
        res = self.creer(est_publie=True)
        self.assertEqual(res.status_code, 400)
        self.assertIn(MESSAGE, str(res.data))
        res = self.creer()
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data['validation_requise'])
        self.assertEqual(res.data['statut_validation'], 'brouillon')
        self.assertEqual(self.patch(res.data['id'], {'est_publie': True}).status_code, 400)

    def test_statut_en_lecture_seule(self):
        self.activer()
        quiz_id = self.creer().data['id']
        res = self.patch(quiz_id, {'statut_validation': 'validee', 'valide_par': self.a.ens.id})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Quiz.objects.get(pk=quiz_id).statut_validation, Quiz.BROUILLON)

    def test_contenu_modifie_depublie(self):
        self.activer()
        quiz_id = self.creer().data['id']
        self.valider_en_base(quiz_id)
        res = self.patch(quiz_id, {'duree_minutes': 45, 'est_publie': True})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['est_publie'], res.data['statut_validation']), (False, 'brouillon'))
        self.valider_en_base(quiz_id)
        question = dict(QUESTION, texte='3 + 3 ?')
        res = self.patch(quiz_id, {'questions': [question]})
        self.assertEqual((res.data['est_publie'], res.data['statut_validation']), (False, 'brouillon'))

    def test_memes_questions_et_organisation_sans_effet(self):
        self.activer()
        quiz_id = self.creer().data['id']
        self.valider_en_base(quiz_id)
        res = self.patch(quiz_id, {'questions': [QUESTION], 'titre': 'Quiz à valider', 'classes': [self.a.classe.id],
                                   'date_fin': '2030-01-01T10:00:00Z'})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['est_publie'], res.data['statut_validation']), (True, 'validee'))

    def test_depublier_puis_republier(self):
        self.activer()
        quiz_id = self.creer().data['id']
        self.valider_en_base(quiz_id)
        self.assertFalse(self.patch(quiz_id, {'est_publie': False}).data['est_publie'])
        res = self.patch(quiz_id, {'est_publie': True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['est_publie'])

    def test_demande_retiree_par_un_changement_de_contenu(self):
        self.activer()
        quiz_id = self.creer().data['id']
        Quiz.objects.filter(pk=quiz_id).update(statut_validation=Quiz.EN_ATTENTE)
        res = self.patch(quiz_id, {'titre': 'Nouveau titre'})
        self.assertEqual(res.data['statut_validation'], 'brouillon')

    def test_gestion_publie_directement(self):
        self.activer()
        res = self.creer(client=client_for(self.a.admin), est_publie=True)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data['est_publie'], res.data['statut_validation']), (True, 'validee'))
        quiz_id = self.creer().data['id']
        res = self.patch(quiz_id, {'est_publie': True}, client=self.resp)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['statut_validation'], 'validee')

    def test_migration_des_quiz_publies(self):
        migration = importlib.import_module('quiz.migrations.0008_validation')
        brouillon = Quiz.objects.create(titre='Brouillon', cree_par=self.a.ens)
        Quiz.objects.filter(pk=self.a.quiz.pk).update(statut_validation=Quiz.BROUILLON)
        migration.marquer_publies_valides(apps, None)
        self.assertEqual(Quiz.objects.get(pk=self.a.quiz.pk).statut_validation, Quiz.VALIDEE)
        self.assertEqual(Quiz.objects.get(pk=brouillon.pk).statut_validation, Quiz.BROUILLON)
