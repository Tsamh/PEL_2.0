from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from referentiel.models import Groupe

G = '/api/referentiel/groupes'


class MembresGroupeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        self.url = f'{G}/{self.groupe.id}/membres/'

    def ajouter(self, user, corps):
        return client_for(user).post(self.url, corps, format='json')

    def test_ajout_d_un_inscrit(self):
        res = self.ajouter(self.a.admin, {'etudiants': [self.a.etu.id]})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual([m['id'] for m in res.data['membres_detail']], [self.a.etu.id])
        self.assertEqual(list(self.groupe.membres.all()), [self.a.etu])
        log = AuditLog.objects.get(action='membre_groupe')
        self.assertEqual(log.details, {'groupe': self.groupe.id, 'etudiants': [self.a.etu.id]})
        self.assertEqual(self.ajouter(self.a.resp, {'etudiants': [self.a.etu.id]}).status_code, 200)

    def test_refus_hors_classe_ou_non_etudiant(self):
        non_inscrit = make_user('noninscrit', 'etudiant', self.a.etab)
        for ids in ([non_inscrit.id], [self.w.b.etu.id], [self.a.ens.id], [self.a.etu.id, 999999]):
            with self.subTest(ids=ids):
                res = self.ajouter(self.a.admin, {'etudiants': ids})
                self.assertEqual(res.status_code, 400)
                self.assertIn('etudiants', res.data)
        self.assertFalse(self.groupe.membres.exists())

    def test_corps_invalides(self):
        for corps in ({}, {'etudiants': []}, {'etudiants': 'x'}, {'etudiants': [True]}, {'etudiants': ['a']}, {'etudiants': [2**70]},
                      {'etudiants': [0]}, {'etudiants': [-1]}, [1]):
            with self.subTest(corps=corps):
                self.assertEqual(self.ajouter(self.a.admin, corps).status_code, 400)

    def test_droits(self):
        self.assertEqual(self.ajouter(self.a.ens, {'etudiants': [self.a.etu.id]}).status_code, 403)
        self.assertEqual(self.ajouter(self.a.etu, {'etudiants': [self.a.etu.id]}).status_code, 403)
        self.assertEqual(self.ajouter(self.w.b.admin, {'etudiants': [self.a.etu.id]}).status_code, 404)
        self.groupe.membres.add(self.a.etu)
        url = f'{self.url}{self.a.etu.id}/'
        self.assertEqual(client_for(self.a.ens).delete(url).status_code, 403)

    def test_retrait(self):
        self.groupe.membres.add(self.a.etu)
        url = f'{self.url}{self.a.etu.id}/'
        self.assertEqual(client_for(self.a.admin).delete(url).status_code, 204)
        self.assertFalse(self.groupe.membres.exists())
        log = AuditLog.objects.get(action='retrait_membre_groupe')
        self.assertEqual(log.details, {'groupe': self.groupe.id, 'etudiant': self.a.etu.id})
        self.assertEqual(client_for(self.a.admin).delete(url).status_code, 404)

    def test_lecture_des_membres(self):
        self.groupe.membres.add(self.a.etu)
        res = client_for(self.a.ens).get(f'{G}/{self.groupe.id}/')
        self.assertEqual([m['id'] for m in res.data['membres_detail']], [self.a.etu.id])
        res = client_for(self.a.etu).get(f'{G}/{self.groupe.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['membres_detail'], [])
