import importlib

from django.apps import apps
from django.core import mail
from django.test import TestCase

from accounts.testing import build_world, client_for
from audit.models import AuditLog
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


class CircuitTests(Base):
    def action(self, quiz_id, nom, client=None, corps=None):
        return (client or self.ens).post(f'{Q}/{quiz_id}/{nom}/', corps or {}, format='json')

    def test_soumission_puis_validation(self):
        self.activer()
        quiz_id = self.creer().data['id']
        res = self.action(quiz_id, 'soumettre_validation')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['statut_validation'], 'en_attente')
        self.assertIsNotNone(res.data['soumis_le'])
        self.assertEqual([m.to for m in mail.outbox], [[self.a.resp.email]])
        self.assertTrue(AuditLog.objects.filter(action='soumission_validation', cible_id=str(quiz_id)).exists())
        self.assertEqual(self.action(quiz_id, 'soumettre_validation').status_code, 409)
        self.assertEqual(self.action(quiz_id, 'valider').status_code, 403)
        self.assertEqual(self.action(quiz_id, 'valider', client_for(self.w.b.resp)).status_code, 404)
        self.assertEqual(self.action(quiz_id, 'valider', client_for(self.a.etu)).status_code, 403)
        res = self.action(quiz_id, 'valider', self.resp)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['statut_validation'], res.data['est_publie']), ('validee', True))
        self.assertEqual(res.data['valide_par'], self.a.resp.id)
        self.assertEqual(mail.outbox[-1].to, [self.a.ens.email])
        self.assertTrue(AuditLog.objects.filter(action='validation_quiz', cible_id=str(quiz_id)).exists())
        self.assertEqual(self.action(quiz_id, 'valider', self.resp).status_code, 409)
        self.assertEqual(self.action(quiz_id, 'soumettre_validation').status_code, 409)

    def test_refus_puis_nouvelle_soumission(self):
        self.activer()
        quiz_id = self.creer().data['id']
        self.action(quiz_id, 'soumettre_validation')
        for corps in ({}, {'motif': '   '}, {'motif': 'x' * 2001}, {'motif': 5}):
            with self.subTest(corps=corps):
                self.assertEqual(self.action(quiz_id, 'refuser', self.resp, corps).status_code, 400)
        res = self.action(quiz_id, 'refuser', self.resp, {'motif': 'Les questions sont trop faciles.'})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['statut_validation'], res.data['est_publie']), ('refusee', False))
        self.assertEqual(res.data['motif_refus'], 'Les questions sont trop faciles.')
        self.assertIn('Les questions sont trop faciles.', mail.outbox[-1].body)
        log = AuditLog.objects.get(action='refus_quiz', cible_id=str(quiz_id))
        self.assertEqual(log.details['motif'], 'Les questions sont trop faciles.')
        self.assertEqual(self.action(quiz_id, 'refuser', self.resp, {'motif': 'Encore'}).status_code, 409)
        res = self.action(quiz_id, 'soumettre_validation')
        self.assertEqual((res.status_code, res.data['statut_validation'], res.data['motif_refus']), (200, 'en_attente', ''))

    def test_soumissions_refusees(self):
        quiz_id = self.creer().data['id']
        self.assertEqual(self.action(quiz_id, 'soumettre_validation').status_code, 409)
        self.activer()
        vide = self.creer(questions=[]).data['id']
        self.assertEqual(self.action(vide, 'soumettre_validation').status_code, 400)
        self.assertEqual(self.action(quiz_id, 'soumettre_validation', client_for(self.w.b.ens)).status_code, 404)
        self.assertEqual(self.action(quiz_id, 'soumettre_validation', client_for(self.a.etu)).status_code, 403)

    def test_file_d_attente(self):
        self.activer()
        attente = self.creer().data['id']
        self.creer()
        self.action(attente, 'soumettre_validation')
        res = self.resp.get(f'{Q}/?statut_validation=en_attente')
        self.assertEqual([q['id'] for q in res.data['results']], [attente])
        self.assertGreater(len(self.resp.get(f'{Q}/?statut_validation=inconnu').data['results']), 1)
        self.assertEqual(client_for(self.w.b.resp).get(f'{Q}/?statut_validation=en_attente').data['results'], [])

    def test_reglage_visible_par_les_createurs(self):
        self.assertEqual(self.ens.get(f'{Q}/validation/').data, {'validation_requise': False})
        self.activer()
        self.assertEqual(self.ens.get(f'{Q}/validation/').data, {'validation_requise': True})
        self.assertEqual(client_for(self.a.etu).get(f'{Q}/validation/').status_code, 403)


class ParametresTests(Base):
    def url(self, etablissement=None):
        return f'/api/referentiel/etablissements/{(etablissement or self.a.etab).id}/parametres/'

    def test_admin_active_le_reglage(self):
        res = client_for(self.a.admin).patch(self.url(), {'validation_quiz_requise': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['validation_quiz_requise'])
        self.a.etab.refresh_from_db()
        self.assertTrue(self.a.etab.validation_quiz_requise)
        self.assertTrue(AuditLog.objects.filter(action='parametres_etablissement').exists())
        self.assertEqual(client_for(self.w.superadmin).patch(self.url(), {'validation_quiz_requise': False},
                                                             format='json').status_code, 200)

    def test_droits_et_valeurs(self):
        self.assertEqual(self.resp.patch(self.url(), {'validation_quiz_requise': True}, format='json').status_code, 403)
        self.assertEqual(self.ens.patch(self.url(), {'validation_quiz_requise': True}, format='json').status_code, 403)
        self.assertEqual(client_for(self.w.b.admin).patch(self.url(), {'validation_quiz_requise': True},
                                                          format='json').status_code, 404)
        for corps in ({'validation_quiz_requise': 'oui'}, {}, [1]):
            with self.subTest(corps=corps):
                self.assertEqual(client_for(self.a.admin).patch(self.url(), corps, format='json').status_code, 400)
        self.assertIn('validation_quiz_requise', self.resp.get(f'/api/referentiel/etablissements/{self.a.etab.id}/').data)


class ContenuHorsFormulaireTests(Base):
    """Les routes questions/ et choix/ ne doivent pas contourner la validation."""

    def setUp(self):
        super().setUp()
        self.activer()
        self.quiz_id = self.creer().data['id']
        self.valider_en_base(self.quiz_id)
        self.question = Quiz.objects.get(pk=self.quiz_id).questions.get()
        self.choix = self.question.choix.order_by('id').first()

    def etat(self):
        quiz = Quiz.objects.get(pk=self.quiz_id)
        return quiz.est_publie, quiz.statut_validation

    def test_modifications_par_l_enseignant_depublient(self):
        requetes = [
            lambda c: c.patch(f'/api/quiz/questions/{self.question.id}/', {'texte': '3 + 3 ?'}, format='json'),
            lambda c: c.patch(f'/api/quiz/choix/{self.choix.id}/', {'est_correct': False}, format='json'),
            lambda c: c.post('/api/quiz/questions/', {'quiz': self.quiz_id, 'texte': 'Nouvelle ?',
                                                      'type_question': 'courte', 'points': '1'}, format='json'),
            lambda c: c.delete(f'/api/quiz/choix/{self.choix.id}/'),
        ]
        for i, requete in enumerate(requetes):
            with self.subTest(requete=i):
                self.valider_en_base(self.quiz_id)
                res = requete(self.ens)
                self.assertLess(res.status_code, 300, getattr(res, 'data', None))
                self.assertEqual(self.etat(), (False, Quiz.BROUILLON))

    def test_modification_par_l_admin_sans_effet(self):
        res = client_for(self.a.admin).patch(f'/api/quiz/questions/{self.question.id}/', {'texte': '3 + 3 ?'},
                                             format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(self.etat(), (True, Quiz.VALIDEE))

    def test_sans_reglage_le_quiz_reste_publie(self):
        self.activer(False)
        self.ens.patch(f'/api/quiz/choix/{self.choix.id}/', {'est_correct': False}, format='json')
        self.assertEqual(self.etat(), (True, Quiz.BROUILLON))


class ReglageEtStatutTests(Base):
    def test_quiz_publie_avant_activation_reste_enregistrable(self):
        quiz_id = self.creer(est_publie=True).data['id']
        self.activer()
        res = self.patch(quiz_id, {'est_publie': True, 'date_fin': '2030-01-01T10:00:00Z'})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['est_publie'])
        res = self.patch(quiz_id, {'est_publie': True, 'duree_minutes': 45})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['est_publie'], res.data['statut_validation']), (False, 'brouillon'))

    def test_statut_valide_perime_sans_reglage(self):
        quiz_id = self.creer().data['id']
        self.valider_en_base(quiz_id)
        res = self.patch(quiz_id, {'est_publie': True, 'duree_minutes': 45})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['est_publie'], res.data['statut_validation']), (True, 'brouillon'))
        self.activer()
        self.assertFalse(self.patch(quiz_id, {'est_publie': False}).data['est_publie'])
        res = self.patch(quiz_id, {'est_publie': True})
        self.assertEqual(res.status_code, 400)
        self.assertIn(MESSAGE, str(res.data))

    def test_publication_par_la_gestion_renseigne_la_validation(self):
        self.activer()
        quiz_id = self.creer().data['id']
        Quiz.objects.filter(pk=quiz_id).update(statut_validation=Quiz.REFUSEE, motif_refus='Trop court')
        res = self.patch(quiz_id, {'est_publie': True}, client=self.resp)
        self.assertEqual(res.status_code, 200, res.data)
        quiz = Quiz.objects.get(pk=quiz_id)
        self.assertEqual((quiz.statut_validation, quiz.valide_par_id, quiz.motif_refus),
                         (Quiz.VALIDEE, self.a.resp.id, ''))
        self.assertIsNotNone(quiz.valide_le)

    def test_la_gestion_ne_soumet_pas(self):
        self.activer()
        quiz_id = self.creer().data['id']
        res = client_for(self.a.admin).post(f'{Q}/{quiz_id}/soumettre_validation/', {}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertIn("Vous pouvez publier ce quiz directement.", str(res.data))

    def test_soumission_sans_responsable_joignable_previent_l_admin(self):
        self.activer()
        self.a.resp.email = ''
        self.a.resp.save()
        quiz_id = self.creer().data['id']
        self.assertEqual(self.ens.post(f'{Q}/{quiz_id}/soumettre_validation/', {}, format='json').status_code, 200)
        self.assertEqual([m.to for m in mail.outbox], [[self.a.admin.email]])

    def test_reglage_en_lecture_seule_dans_le_referentiel(self):
        res = client_for(self.w.superadmin).patch(f'/api/referentiel/etablissements/{self.a.etab.id}/',
                                                  {'validation_quiz_requise': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.a.etab.refresh_from_db()
        self.assertFalse(self.a.etab.validation_quiz_requise)
