"""Accusé de réception d'une soumission de devoir (sous-projet 4c, tâche 4)."""
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from accounts.testing import build_world, client_for
from programming.models import Devoir, Execution, SoumissionDevoir

P = '/api/programming'


@override_settings(PEL_EXECUTEUR='factice')
class AccuseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.etu = client_for(self.a.etu)
        Devoir.objects.filter(pk=self.a.devoir.pk).update(resoumission_autorisee=True,
                                                          politique_resultats=Devoir.IMMEDIATE)

    def soumettre(self):
        corps = {'devoir': self.a.devoir.id,
                 'reponses': [{'exercice': self.a.exercice.id, 'fichiers': [{'nom': 'main.py', 'contenu': 'x'}]}]}
        with self.captureOnCommitCallbacks(execute=True):
            return self.etu.post(f'{P}/soumissions/', corps, format='json')

    def test_creation(self):
        self.assertEqual(self.soumettre().status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.a.etu.email])
        self.assertEqual(message.subject, f"Accusé de réception : {self.a.devoir.titre}")
        self.assertIn(self.a.devoir.titre, message.body)
        self.assertNotIn('version', message.body.lower())
        self.assertNotIn('automatiquement', message.body)

    def test_resoumission_indique_la_version(self):
        self.soumettre()
        SoumissionDevoir.objects.update(statut=SoumissionDevoir.CORRIGEE_AUTO, note_proposee=Decimal('12.50'))
        Execution.objects.update(statut=Execution.TERMINEE)
        self.assertEqual(self.soumettre().status_code, 201)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('version n°2', mail.outbox[1].body)

    def test_sans_email_rien(self):
        type(self.a.etu).objects.filter(pk=self.a.etu.pk).update(email='')
        self.etu = client_for(type(self.a.etu).objects.get(pk=self.a.etu.pk))
        self.assertEqual(self.soumettre().status_code, 201)
        self.assertEqual(mail.outbox, [])

    def test_echec_d_envoi_sans_effet(self):
        with mock.patch('programming.accuses.send_mail', side_effect=OSError('smtp')):
            res = self.soumettre()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(SoumissionDevoir.objects.count(), 1)

    def test_aucune_note_dans_le_texte(self):
        self.soumettre()
        SoumissionDevoir.objects.update(statut=SoumissionDevoir.CORRIGEE_AUTO, note_proposee=Decimal('12.50'),
                                        score=13)
        Execution.objects.update(statut=Execution.TERMINEE)
        self.soumettre()
        for message in mail.outbox:
            for interdit in ('12.50', '12,5', 'note', 'résultat', 'score'):
                self.assertNotIn(interdit, message.body.lower())

    def test_soumission_automatique(self):
        from programming.accuses import envoyer_accuse
        self.soumettre()
        SoumissionDevoir.objects.update(soumission_auto=True)
        envoyer_accuse(SoumissionDevoir.objects.get())
        self.assertIn("Il a été soumis automatiquement à la fermeture, avec votre dernier enregistrement.",
                      mail.outbox[-1].body)

    def test_pas_d_envoi_si_annulation(self):
        corps = {'devoir': self.a.devoir.id, 'reponses': []}
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.etu.post(f'{P}/soumissions/', corps, format='json').status_code, 400)
        self.assertEqual(mail.outbox, [])
