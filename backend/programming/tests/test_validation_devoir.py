from django.core import mail
from django.test import TestCase

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from programming.models import Devoir
from referentiel.models import AnneeAcademique

P = '/api/programming/devoirs'
MESSAGE = "La publication de ce devoir demande la validation du responsable de formation."
EXERCICE = {'titre': 'Somme', 'points': '5', 'tests': [{'entree': '1 2', 'sortie_attendue': '3', 'public': True}]}


class ValidationDevoirTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.ens = client_for(self.a.ens)
        self.resp = client_for(self.a.resp)
        self.a.etab.validation_quiz_requise = True
        self.a.etab.save()

    def creer(self, client=None, **extra):
        corps = {'titre': 'Devoir à valider', 'filiere': self.a.filiere.id, 'exercices': [EXERCICE], **extra}
        return (client or self.ens).post(f'{P}/', corps, format='json')

    def action(self, devoir_id, nom, client=None, **corps):
        return (client or self.ens).post(f'{P}/{devoir_id}/{nom}/', corps, format='json')

    def test_publication_directe_refusee(self):
        res = self.creer(est_publie=True)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['est_publie'][0]), MESSAGE)
        res = self.creer()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data['validation_requise'])
        self.assertEqual(res.data['statut_validation'], 'brouillon')
        patch = self.ens.patch(f'{P}/{res.data["id"]}/', {'est_publie': True}, format='json')
        self.assertEqual(patch.status_code, 400)

    def test_circuit_complet(self):
        devoir_id = self.creer().data['id']
        res = self.action(devoir_id, 'soumettre_validation')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['statut_validation'], 'en_attente')
        self.assertTrue(AuditLog.objects.filter(action='soumission_validation', details__type='devoir').exists())
        self.assertTrue(any('Devoir à valider' in m.subject for m in mail.outbox))
        self.assertEqual(self.action(devoir_id, 'soumettre_validation').status_code, 409)
        res = self.action(devoir_id, 'valider', client=self.resp)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['statut_validation'], res.data['est_publie']), ('validee', True))
        self.assertTrue(AuditLog.objects.filter(action='validation_quiz', details__type='devoir').exists())
        res = self.ens.patch(f'{P}/{devoir_id}/', {'consignes': 'Nouvelles consignes'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['statut_validation'], res.data['est_publie']), ('brouillon', False))

    def test_refus_avec_motif(self):
        devoir_id = self.creer().data['id']
        self.action(devoir_id, 'soumettre_validation')
        self.assertEqual(self.action(devoir_id, 'refuser', client=self.resp).status_code, 400)
        res = self.action(devoir_id, 'refuser', client=self.resp, motif='Tests insuffisants')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['statut_validation'], res.data['motif_refus']), ('refusee', 'Tests insuffisants'))
        self.assertTrue(AuditLog.objects.filter(action='refus_quiz', details__type='devoir').exists())

    def test_courriel_de_validation(self):
        devoir_id = self.creer().data['id']
        self.action(devoir_id, 'soumettre_validation')
        mail.outbox.clear()
        self.action(devoir_id, 'valider', client=self.resp)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.a.ens.email])
        self.assertEqual(message.subject, 'Devoir validé : Devoir à valider')
        self.assertIn('est maintenant publié', message.body)

    def test_courriel_de_refus(self):
        devoir_id = self.creer().data['id']
        self.action(devoir_id, 'soumettre_validation')
        mail.outbox.clear()
        self.action(devoir_id, 'refuser', client=self.resp, motif='Tests insuffisants')
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.a.ens.email])
        self.assertEqual(message.subject, 'Devoir à revoir : Devoir à valider')
        self.assertIn('Motif : Tests insuffisants', message.body)

    def test_gestion_publie_directement(self):
        res = self.creer(client=self.resp, est_publie=True)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data['est_publie'], res.data['statut_validation']), (True, 'validee'))
        self.assertEqual(self.action(res.data['id'], 'soumettre_validation', client=self.resp).status_code, 409)

    def test_droits(self):
        devoir_id = self.creer().data['id']
        self.action(devoir_id, 'soumettre_validation')
        self.assertEqual(self.action(devoir_id, 'valider').status_code, 403)
        self.assertEqual(self.action(devoir_id, 'refuser', motif='x').status_code, 403)
        self.assertEqual(self.action(devoir_id, 'valider', client=client_for(self.a.etu)).status_code, 403)
        self.assertEqual(self.action(devoir_id, 'valider', client=client_for(self.w.b.resp)).status_code, 404)
        self.assertEqual(self.action(devoir_id, 'soumettre_validation', client=client_for(self.w.b.ens)).status_code, 404)
        self.assertEqual(Devoir.objects.get(pk=devoir_id).statut_validation, Devoir.EN_ATTENTE)

    def test_sans_exercice(self):
        devoir_id = self.creer(exercices=[]).data['id']
        res = self.action(devoir_id, 'soumettre_validation')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['detail']), "Ajoutez au moins un exercice avant de soumettre le devoir.")

    def test_filtre_statut_validation(self):
        attente = self.creer().data['id']
        brouillon = self.creer(titre='Autre').data['id']
        self.action(attente, 'soumettre_validation')
        res = self.resp.get(f'{P}/', {'statut_validation': 'en_attente'})
        donnees = res.data['results'] if 'results' in res.data else res.data
        ids = [d['id'] for d in donnees]
        self.assertIn(attente, ids)
        self.assertNotIn(brouillon, ids)

    def test_annee_archivee(self):
        devoir_id = self.creer(annee_academique=self.a.annee.id).data['id']
        self.action(devoir_id, 'soumettre_validation')
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        for nom, client, corps in (('soumettre_validation', self.ens, {}), ('valider', self.resp, {}),
                                   ('refuser', self.resp, {'motif': 'x'})):
            with self.subTest(action=nom):
                res = self.action(devoir_id, nom, client=client, **corps)
                self.assertEqual(res.status_code, 409)
                self.assertIn('est archivée', str(res.data['detail']))
        self.assertEqual(Devoir.objects.get(pk=devoir_id).statut_validation, Devoir.EN_ATTENTE)
