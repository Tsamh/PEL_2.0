from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from audit.services import log


def requete(user, ip='10.0.0.7'):
    request = RequestFactory().get('/', REMOTE_ADDR=ip)
    request.user = user
    return request


class ServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_log_enregistre_acteur_role_ip_et_cible(self):
        a = self.w.a
        entree = log(requete(a.admin), 'desactivation', cible=a.etu, details={'motif': 'test'})
        self.assertEqual(entree.acteur, a.admin)
        self.assertEqual(entree.role_acteur, 'admin')
        self.assertEqual(entree.etablissement, a.etab)
        self.assertEqual(entree.cible_type, 'user')
        self.assertEqual(entree.cible_id, str(a.etu.pk))
        self.assertEqual(entree.details, {'motif': 'test'})
        self.assertEqual(entree.ip, '10.0.0.7')

    def test_etablissement_de_la_cible_prioritaire_pour_le_superadmin(self):
        entree = log(requete(self.w.superadmin), 'validation_admin', cible=self.w.b.admin)
        self.assertEqual(entree.etablissement, self.w.b.etab)

    def test_echec_ecriture_ne_leve_pas(self):
        with mock.patch.object(AuditLog.objects, 'create', side_effect=RuntimeError('db')):
            self.assertIsNone(log(requete(self.w.a.admin), 'export'))

    def test_echec_ecriture_dans_transaction_ne_la_casse_pas(self):
        with transaction.atomic():
            with mock.patch.object(AuditLog.objects, 'create', side_effect=IntegrityError('db')):
                self.assertIsNone(log(requete(self.w.a.admin), 'export'))
            self.assertGreaterEqual(AuditLog.objects.count(), 0)

    def test_journal_immuable(self):
        entree = log(requete(self.w.a.admin), 'export')
        entree.action = 'login_succes'
        with self.assertRaises(ValueError):
            entree.save()
        with self.assertRaises(ValueError):
            entree.delete()


class EndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        log(requete(cls.w.a.admin), 'desactivation', cible=cls.w.a.etu)
        log(requete(cls.w.b.admin), 'desactivation', cible=cls.w.b.etu)
        log(requete(cls.w.a.admin), 'export')

    def test_superadmin_voit_tout(self):
        res = client_for(self.w.superadmin).get('/api/audit/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 3)

    def test_admin_voit_son_etablissement(self):
        res = client_for(self.w.a.admin).get('/api/audit/')
        self.assertEqual(res.data['count'], 2)
        self.assertTrue(all(e['etablissement'] == self.w.a.etab.id for e in res.data['results']))

    def test_autres_roles_refuses(self):
        a = self.w.a
        for user in (a.resp, a.ens, a.etu):
            with self.subTest(role=user.role):
                self.assertEqual(client_for(user).get('/api/audit/').status_code, 403)

    def test_filtres(self):
        client = client_for(self.w.superadmin)
        self.assertEqual(client.get('/api/audit/?action=export').data['count'], 1)
        self.assertEqual(client.get(f'/api/audit/?acteur={self.w.b.admin.id}').data['count'], 1)
        self.assertEqual(client.get('/api/audit/?date_debut=2000-01-01&date_fin=2999-12-31').data['count'], 3)
        self.assertEqual(client.get('/api/audit/?date_debut=pas-une-date').data['count'], 3)
        self.assertEqual(client.get('/api/audit/?acteur=abc').data['count'], 3)

    def test_lecture_seule(self):
        self.assertEqual(client_for(self.w.superadmin).post('/api/audit/', {}).status_code, 405)


class FiltreActeurRobusteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_acteur_non_ascii_ignore(self):
        for valeur in ('²', '١٢', '٣'):
            res = client_for(self.w.superadmin).get(f'/api/audit/?acteur={valeur}')
            self.assertEqual(res.status_code, 200, valeur)
